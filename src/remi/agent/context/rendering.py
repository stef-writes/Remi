"""LLM context rendering — projects typed perception into prose for injection.

``render_domain_context`` renders TBox knowledge for agent priming (once).
``render_active_signals`` renders ABox perception for per-turn injection.
``render_graph_context`` renders entity neighborhood for per-turn injection.
"""

from __future__ import annotations

import re
from typing import Any

import structlog

from remi.agent.context.frame import ContextFrame
from remi.agent.signals import DomainTBox, MutableTBox, Signal
from remi.agent.vectors.types import Embedder
from remi.types.text import estimate_tokens

_log = structlog.get_logger(__name__)


def render_domain_context(domain: Any, *, compact: bool = False) -> str:
    """Render the TBox into a system message block for agent priming.

    When *compact* is True, only signal names/severities and composition
    rules are emitted — thresholds, policies, and causal chains are
    omitted.  Use compact mode for agents that query signals via tools
    rather than reasoning over the full ontology (e.g. researcher).
    """
    if isinstance(domain, MutableTBox):
        pass
    elif not isinstance(domain, DomainTBox):
        return ""

    shape_parts: list[str] = []
    sig_count = len(getattr(domain, "signals", {}))
    thr_count = len(getattr(domain, "thresholds", {}))
    pol_count = len(getattr(domain, "policies", []))
    cc_count = len(getattr(domain, "causal_chains", []))
    if sig_count:
        shape_parts.append(f"{sig_count} signals")
    if not compact:
        if thr_count:
            shape_parts.append(f"{thr_count} thresholds")
        if pol_count:
            shape_parts.append(f"{pol_count} policies")
        if cc_count:
            shape_parts.append(f"{cc_count} causal chains")
    shape_label = f"TBox: {', '.join(shape_parts)}" if shape_parts else "from TBox"
    parts = [f"## Domain Context ({shape_label})\n"]

    signals = getattr(domain, "signals", {})
    if signals:
        signal_lines = []
        for defn in signals.values() if isinstance(signals, dict) else signals:
            if compact:
                signal_lines.append(f"- {defn.name} [{defn.severity.value}] ({defn.entity})")
            else:
                desc = defn.description.split("\n")[0].strip()
                signal_lines.append(
                    f"- **{defn.name}** [{defn.severity.value}] ({defn.entity}): {desc}"
                )
        parts.append("**Signal definitions (what the entailment engine detects):**")
        parts.append("\n".join(signal_lines))

    if not compact:
        thresholds = getattr(domain, "thresholds", {})
        if thresholds:
            threshold_lines = [f"- {key}: {val}" for key, val in thresholds.items()]
            parts.append("\n**Operational thresholds:**")
            parts.append("\n".join(threshold_lines))

        policies = getattr(domain, "policies", [])
        if policies:
            policy_lines = [f"- [{pol.deontic.value}] {pol.description}" for pol in policies]
            parts.append("\n**Deontic obligations:**")
            parts.append("\n".join(policy_lines))

        causal_chains = getattr(domain, "causal_chains", [])
        if causal_chains:
            chain_lines = [f"- {c.cause} → {c.effect}: {c.description}" for c in causal_chains]
            parts.append("\n**Known causal relationships:**")
            parts.append("\n".join(chain_lines))

    compositions = getattr(domain, "compositions", [])
    if compositions:
        comp_lines = []
        for comp in compositions:
            sev = comp.severity.value if hasattr(comp.severity, "value") else str(comp.severity)
            constituents = " + ".join(comp.constituents)
            comp_lines.append(
                f"- **{comp.name}** [{sev}] = {constituents}: "
                f"{comp.description.split(chr(10))[0].strip()}"
            )
        parts.append("\n**Composition rules (compound signals from co-occurring signals):**")
        parts.append("\n".join(comp_lines))

    parts.append("\nComposition signals indicate compounding situations — prioritize them.")
    return "\n".join(parts)


async def render_active_signals(
    signal_store: Any,
    *,
    question: str | None = None,
    embedder: Embedder | None = None,
    max_signals: int = 15,
) -> str:
    """Fetch current signals, rank by semantic relevance, and render a compact summary."""
    try:
        signals = await signal_store.list_signals()
    except Exception:
        _log.warning("signal_summary_fetch_failed", exc_info=True)
        return ""

    if not signals:
        return (
            "## Active Signals (0)\n\n"
            "No signals currently active. The portfolio appears within normal parameters. "
            "If the user asks about problems, verify by querying the data directly."
        )

    ranked = await _rank_signals(signals, question, embedder)
    ranked = ranked[:max_signals]

    severity_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "⚪"}

    severity_counts: dict[str, int] = {}
    for s in signals:
        sev = s.severity.value if hasattr(s.severity, "value") else str(s.severity)
        severity_counts[sev] = severity_counts.get(sev, 0) + 1
    sev_order = ["critical", "high", "medium", "low"]
    breakdown = ", ".join(
        f"{severity_counts[sev]} {sev}" for sev in sev_order if severity_counts.get(sev)
    )
    header = f"{len(signals)} total: {breakdown}" if breakdown else f"{len(signals)} total"
    lines = [f"## Active Signals ({header}, showing top {len(ranked)})\n"]
    for s in ranked:
        sev_val = s.severity.value if hasattr(s.severity, "value") else str(s.severity)
        icon = severity_icon.get(sev_val, "❓")
        desc = s.description[:120] + ("…" if len(s.description) > 120 else "")
        lines.append(
            f"- {icon} **[{sev_val.upper()}] {s.signal_type}**: "
            f"{s.entity_name} — {desc}  \n"
            f"  `{s.signal_id}`"
        )

    lines.append(
        "\nThese signals are pre-computed from the data. Reference them by name in your response."
    )
    return "\n".join(lines)


async def _rank_signals(
    signals: list[Signal],
    question: str | None,
    embedder: Embedder | None = None,
) -> list[Signal]:
    """Rank signals by semantic relevance to the question."""
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}

    def _signal_text(s: Signal) -> str:
        return f"{s.signal_type} {s.entity_name} {s.description}"

    similarity_scores: dict[str, float] = {}
    if question and embedder is not None:
        try:
            signal_texts = [_signal_text(s) for s in signals]
            all_texts = [question] + signal_texts
            all_vectors = await embedder.embed(all_texts)

            question_vec = all_vectors[0]
            for i, s in enumerate(signals):
                signal_vec = all_vectors[i + 1]
                dot = sum(a * b for a, b in zip(question_vec, signal_vec, strict=True))
                norm_q = sum(a * a for a in question_vec) ** 0.5
                norm_s = sum(a * a for a in signal_vec) ** 0.5
                denom = norm_q * norm_s
                similarity_scores[s.signal_id] = dot / denom if denom else 0.0
        except Exception:
            _log.debug("embedding_signal_rank_failed", exc_info=True)

    keyword_scores: dict[str, int] = {}
    if not similarity_scores and question:
        question_words = {w.lower() for w in re.findall(r"[a-zA-Z]{3,}", question)}
        for s in signals:
            haystack_words = set(re.findall(r"[a-zA-Z]{3,}", _signal_text(s).lower()))
            keyword_scores[s.signal_id] = len(question_words & haystack_words)

    def sort_key(s: Signal) -> tuple[int, int, float, str]:
        sev = s.severity.value if hasattr(s.severity, "value") else str(s.severity)
        tier = severity_order.get(sev, 4)
        is_composite = "composition_rule" in (s.evidence or {})
        composite_boost = 0 if is_composite else 1

        if similarity_scores:
            relevance = -similarity_scores.get(s.signal_id, 0.0)
        else:
            relevance = -float(keyword_scores.get(s.signal_id, 0))

        return (composite_boost, tier, relevance, s.signal_type)

    return sorted(signals, key=sort_key)


def render_graph_context(
    frame: ContextFrame,
    *,
    max_entities: int = 5,
    max_links_per_entity: int = 10,
    max_tokens: int = 4000,
) -> str:
    """Render resolved entities and their graph neighborhood for the LLM."""
    if not frame.entities:
        return ""

    entities = sorted(frame.entities, key=lambda e: e.score, reverse=True)[:max_entities]
    entity_ids = {e.entity_id for e in entities}
    entity_signals: dict[str, list[Signal]] = {}
    for s in frame.signals:
        if s.entity_id in entity_ids:
            entity_signals.setdefault(s.entity_id, []).append(s)

    lines = [f"## Graph Context ({len(entities)} relevant entities)\n"]
    token_count = estimate_tokens("\n".join(lines))

    for entity in entities:
        entity_lines: list[str] = []
        name = entity.properties.get("name", entity.entity_id)
        entity_lines.append(
            f"### {entity.entity_type}: {name}"
            f"  (id=`{entity.entity_id}`, relevance={entity.score:.2f})"
        )

        display_props = {
            k: v for k, v in entity.properties.items() if k not in ("text",) and v is not None
        }
        if display_props:
            prop_parts = [f"{k}={v}" for k, v in list(display_props.items())[:8]]
            entity_lines.append(f"  Properties: {', '.join(prop_parts)}")

        links = frame.neighborhood.get(entity.entity_id, [])[:max_links_per_entity]
        if links:
            entity_lines.append("  Relationships:")
            for link in links:
                direction = "→" if link.source_id == entity.entity_id else "←"
                other_id = link.target_id if link.source_id == entity.entity_id else link.source_id
                entity_lines.append(f"  - {direction} {link.link_type} → `{other_id}`")

        sigs = entity_signals.get(entity.entity_id, [])
        for sig in sigs:
            sev = sig.severity.value if hasattr(sig.severity, "value") else str(sig.severity)
            entity_lines.append(
                f"  Active signal: [{sev.upper()}] {sig.signal_type} — {sig.description[:100]}"
            )

        entity_lines.append("")

        chunk_cost = estimate_tokens("\n".join(entity_lines))
        if token_count + chunk_cost > max_tokens:
            break
        lines.extend(entity_lines)
        token_count += chunk_cost

    if len(lines) <= 1:
        return ""

    lines.append(
        "This graph context was pre-fetched based on your question. Use it to ground your answer."
    )
    return "\n".join(lines)


def extract_signal_references(text: str, domain: Any) -> list[str]:
    """Find signal names mentioned in the agent's output."""
    if domain is None or not hasattr(domain, "all_signal_names"):
        return []
    found = []
    for name in domain.all_signal_names():
        if re.search(rf"\b{re.escape(name)}\b", text, re.IGNORECASE):
            found.append(name)
    return found
