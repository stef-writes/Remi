#!/usr/bin/env python3
"""End-to-end dry run: load Alex's data → ingest → entailment → signals → trace.

Validates the full pipeline without needing an LLM key. Run from the project root:

    .venv/bin/python scripts/dry_run.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure src is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

console = Console()

DATA_DIR = Path(__file__).resolve().parent.parent / "src" / "remi" / "data" / "sample_reports" / "Alex_Budavich_Reports"

FILES = [
    ("Rent Roll_Vacancy (1).xlsx", "Alex Budavich"),
    ("Delinquency.xlsx", "Alex Budavich"),
    ("Lease Expiration Detail By Month.xlsx", "Alex Budavich"),
]


async def main() -> None:
    console.print(Rule("[bold cyan]REMI Dry Run — Alex Budavich Data[/bold cyan]", style="cyan"))
    console.print()

    # ── 1. Bootstrap container ────────────────────────────────────────
    console.print("[dim]Bootstrapping container...[/dim]")
    from remi.infrastructure.config.container import Container
    from remi.infrastructure.config.settings import load_settings
    from remi.infrastructure.observability.logging import configure_logging

    settings = load_settings()
    configure_logging(level="WARNING", format="text")
    container = Container(settings)
    await container.ensure_bootstrapped()
    console.print("[green]✓[/green] Container bootstrapped\n")

    # ── 2. Ingest all three reports ───────────────────────────────────
    console.print(Rule("[bold yellow]Phase 1: Document Ingestion[/bold yellow]", style="yellow"))
    console.print()

    for filename, manager_tag in FILES:
        filepath = DATA_DIR / filename
        if not filepath.exists():
            console.print(f"[red]✗ Missing:[/red] {filepath}")
            continue

        content = filepath.read_bytes()
        content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

        result = await container.document_ingest.ingest_upload(
            filename=filename,
            content=content,
            content_type=content_type,
            manager=manager_tag,
        )

        console.print(f"  [green]✓[/green] {filename}")
        console.print(f"    Report type: [cyan]{result.report_type}[/cyan]")
        console.print(f"    Entities:    {result.entities_extracted}")
        console.print(f"    Relations:   {result.relationships_extracted}")
        if result.ambiguous_rows:
            console.print(f"    Ambiguous:   {result.ambiguous_rows}")
        console.print()

    # ── 3. Inspect PropertyStore contents ─────────────────────────────
    console.print(Rule("[bold yellow]Phase 2: PropertyStore State[/bold yellow]", style="yellow"))
    console.print()

    ps = container.property_store
    managers = await ps.list_managers()
    portfolios = await ps.list_portfolios()
    properties = await ps.list_properties()
    units = await ps.list_units()
    tenants = await ps.list_tenants()
    leases = await ps.list_leases()

    store_table = Table(title="PropertyStore Counts", show_header=True)
    store_table.add_column("Entity", style="cyan")
    store_table.add_column("Count", justify="right")
    store_table.add_row("Managers", str(len(managers)))
    store_table.add_row("Portfolios", str(len(portfolios)))
    store_table.add_row("Properties", str(len(properties)))
    store_table.add_row("Units", str(len(units)))
    store_table.add_row("Tenants", str(len(tenants)))
    store_table.add_row("Leases", str(len(leases)))
    console.print(store_table)
    console.print()

    if managers:
        console.print("  Managers:")
        for m in managers:
            console.print(f"    {m.id}: {m.name}")
    if properties:
        console.print(f"\n  Properties (showing first 10 of {len(properties)}):")
        for p in properties[:10]:
            console.print(f"    {p.id}: {p.name} [dim](portfolio: {p.portfolio_id})[/dim]")
    console.print()

    # ── 4. Run signal pipeline (rule-based + statistical) ────────────
    console.print(Rule("[bold yellow]Phase 3: Signal Pipeline[/bold yellow]", style="yellow"))
    console.print()

    pipeline_result = await container.signal_pipeline.run_all()

    console.print(f"  Signals produced: [bold]{pipeline_result.produced}[/bold]")
    for source, pr in pipeline_result.per_source.items():
        console.print(f"    {source}: {pr.produced} signals, {pr.errors} errors")
    if pipeline_result.trace_id:
        console.print(f"  Trace ID:         [cyan]{pipeline_result.trace_id}[/cyan]")
    console.print()

    # ── 5. Display signals ────────────────────────────────────────────
    console.print(Rule("[bold yellow]Phase 4: Active Signals[/bold yellow]", style="yellow"))
    console.print()

    signals = await container.signal_store.list_signals()
    if not signals:
        console.print("  [dim]No signals produced.[/dim]")
    else:
        severity_icons = {
            "critical": "[red]●[/red]",
            "high": "[bright_red]●[/bright_red]",
            "medium": "[yellow]●[/yellow]",
            "low": "[dim]●[/dim]",
        }

        sig_table = Table(title=f"{len(signals)} Active Signal(s)", show_header=True)
        sig_table.add_column("Sev", width=5, justify="center")
        sig_table.add_column("Signal Type", style="cyan")
        sig_table.add_column("Entity")
        sig_table.add_column("Description", max_width=60)

        for s in sorted(signals, key=lambda x: ["critical", "high", "medium", "low"].index(x.severity.value) if x.severity.value in ["critical", "high", "medium", "low"] else 99):
            icon = severity_icons.get(s.severity.value, "?")
            sig_table.add_row(icon, s.signal_type, s.entity_name, s.description[:60])

        console.print(sig_table)
        console.print()

        console.print("  Signal detail (first 3):")
        for s in signals[:3]:
            console.print(f"\n    [bold]{s.signal_type}[/bold] [{s.severity.value.upper()}]")
            console.print(f"    Entity: {s.entity_name} ({s.entity_type})")
            console.print(f"    {s.description}")
            console.print(f"    Evidence keys: {list(s.evidence.keys())}")

    console.print()

    # ── 6. Inspect trace ──────────────────────────────────────────────
    console.print(Rule("[bold yellow]Phase 5: Trace Inspection[/bold yellow]", style="yellow"))
    console.print()

    if pipeline_result.trace_id:
        spans = await container.trace_store.list_spans(pipeline_result.trace_id)
        console.print(f"  Trace [cyan]{pipeline_result.trace_id}[/cyan]: {len(spans)} span(s)\n")

        trace_table = Table(show_header=True)
        trace_table.add_column("Kind", style="cyan", width=14)
        trace_table.add_column("Name")
        trace_table.add_column("Duration", justify="right")
        trace_table.add_column("Events", justify="right")

        for span in spans[:20]:
            dur = f"{span.duration_ms:.0f}ms" if span.duration_ms else "..."
            trace_table.add_row(
                span.kind.value,
                span.name[:40],
                dur,
                str(len(span.events)),
            )

        console.print(trace_table)

        console.print(f"\n  [dim]Run: remi trace show {pipeline_result.trace_id}[/dim]")
    else:
        console.print("  [dim]No trace captured (tracer not wired).[/dim]")

    # ── 7. Test ontology CLI tools (programmatic) ─────────────────────
    console.print()
    console.print(Rule("[bold yellow]Phase 6: Ontology Queries[/bold yellow]", style="yellow"))
    console.print()

    os = container.knowledge_graph
    types = await os.list_object_types()
    console.print(f"  Object types: {len(types)}")
    for t in types:
        console.print(f"    {t.name}")

    link_types = await os.list_link_types()
    console.print(f"\n  Link types: {len(link_types)}")

    if properties:
        first_prop = properties[0]
        result = await os.search_objects("Property", limit=5)
        console.print(f"\n  onto search Property: {len(result)} result(s)")

    # ── 8. Domain ontology TBox summary ───────────────────────────────
    console.print()
    console.print(Rule("[bold yellow]Phase 7: TBox Summary[/bold yellow]", style="yellow"))
    console.print()

    domain = container.domain_rulebook
    console.print(f"  Signal definitions: {len(domain.signals)}")
    for name, defn in domain.signals.items():
        console.print(f"    {name}: {defn.severity.value} | {defn.rule.condition.value} | entity={defn.entity}")

    console.print(f"\n  Thresholds: {len(domain.thresholds)}")
    for k, v in domain.thresholds.items():
        console.print(f"    {k}: {v}")

    console.print(f"\n  Policies: {len(domain.policies)}")
    for p in domain.policies:
        console.print(f"    [{p.deontic.value.upper()}] {p.description[:80]}")

    console.print(f"\n  Causal chains: {len(domain.causal_chains)}")

    # ── Summary ───────────────────────────────────────────────────────
    console.print()
    console.print(Rule("[bold green]Dry Run Complete[/bold green]", style="green"))
    console.print()

    summary = Table.grid(padding=(0, 2))
    summary.add_column(style="dim")
    summary.add_column()
    summary.add_row("Documents ingested", str(len(FILES)))
    summary.add_row("Properties loaded", str(len(properties)))
    summary.add_row("Units loaded", str(len(units)))
    summary.add_row("Tenants loaded", str(len(tenants)))
    summary.add_row("Leases loaded", str(len(leases)))
    summary.add_row("Signals produced", str(len(signals)))
    summary.add_row("Trace spans", str(len(spans)) if pipeline_result.trace_id else "0")

    console.print(Panel(summary, title="[bold]Summary[/bold]", border_style="green"))

    if signals:
        console.print(f"\n[bold]Next steps:[/bold]")
        console.print(f"  remi onto signals             — view all signals")
        console.print(f"  remi onto explain <signal-id>  — drill into evidence")
        if pipeline_result.trace_id:
            console.print(f"  remi trace show {pipeline_result.trace_id} — full signal pipeline trace")
        console.print(f"  remi chat --agent director    — ask the AI (needs OPENAI_API_KEY)")
    console.print()


if __name__ == "__main__":
    asyncio.run(main())
