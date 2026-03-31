"""Intent classifier — lightweight heuristic routing for agent execution.

Classifies the user's last message into a declared intent so the agent
loop can run with a right-sized tool surface, iteration cap, and context
injection profile.  Pure heuristics, no LLM call — runs in <1ms.
"""

from __future__ import annotations

import re
from typing import Any

import structlog

from remi.agent.config import IntentConfig

logger = structlog.get_logger("remi.agent.intent")

_GREETING_PATTERNS = re.compile(
    r"^(hi|hello|hey|howdy|good\s+(morning|afternoon|evening)|thanks|thank\s+you|bye|goodbye)\b",
    re.IGNORECASE,
)
_QUESTION_MARK = re.compile(r"\?\s*$")

_ACTION_KEYWORDS = frozenset({
    "create action", "draft plan", "action plan", "action item",
    "follow-up", "follow up", "approve plan", "assign",
})
_DEEP_DIVE_KEYWORDS = frozenset({
    "build", "chart", "audit", "report", "trend", "visualization",
    "export", "write a report", "deep dive", "investigate",
    "comprehensive", "detailed analysis",
})
_ANALYSIS_KEYWORDS = frozenset({
    "compare", "analyze", "analysis", "which", "rank", "breakdown",
    "summarize", "overview", "assess", "evaluate", "review",
    "underperforming", "top", "worst", "best",
})


def classify_intent(
    message: str | None,
    intents: dict[str, IntentConfig],
) -> tuple[str, IntentConfig] | None:
    """Classify a user message into a declared intent.

    Returns ``(intent_name, intent_config)`` or ``None`` if no intents
    are declared or the message is empty.
    """
    if not intents or not message:
        return None

    text = message.strip()
    text_lower = text.lower()
    word_count = len(text.split())

    if "conversation" in intents and _is_conversation(text, text_lower, word_count):
        return ("conversation", intents["conversation"])

    if "action" in intents and _matches_keywords(text_lower, _ACTION_KEYWORDS):
        return ("action", intents["action"])

    if "deep_dive" in intents and _matches_keywords(text_lower, _DEEP_DIVE_KEYWORDS):
        return ("deep_dive", intents["deep_dive"])

    if "analysis" in intents and _matches_keywords(text_lower, _ANALYSIS_KEYWORDS):
        return ("analysis", intents["analysis"])

    for name, intent_cfg in intents.items():
        if name in ("conversation", "action", "deep_dive", "analysis", "lookup"):
            continue
        if intent_cfg.keywords and _matches_keywords(text_lower, frozenset(intent_cfg.keywords)):
            return (name, intent_cfg)

    if "lookup" in intents and _is_lookup(text, text_lower, word_count):
        return ("lookup", intents["lookup"])

    fallback = intents.get("analysis") or intents.get("lookup")
    if fallback:
        name = "analysis" if "analysis" in intents else "lookup"
        return (name, fallback)

    return None


def _is_conversation(text: str, text_lower: str, word_count: int) -> bool:
    if _GREETING_PATTERNS.match(text_lower):
        return True
    if word_count <= 5 and not _QUESTION_MARK.search(text):
        conversational = {"what can you do", "help", "who are you", "capabilities"}
        if any(phrase in text_lower for phrase in conversational):
            return True
    return False


def _is_lookup(text: str, text_lower: str, word_count: int) -> bool:
    if word_count <= 20 and _QUESTION_MARK.search(text):
        return True
    lookup_phrases = {"how many", "show me", "what is", "what's", "list", "get"}
    if any(phrase in text_lower for phrase in lookup_phrases):
        return True
    return False


def _matches_keywords(text_lower: str, keywords: frozenset[str]) -> bool:
    return any(kw in text_lower for kw in keywords)
