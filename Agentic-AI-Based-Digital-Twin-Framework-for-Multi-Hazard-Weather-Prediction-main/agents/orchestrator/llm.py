"""
Thin LLM wrapper used by every orchestrator node that needs language
understanding or generation (intent understanding, task planning, final
response generation).

If GROQ_API_KEY is not set, falls back to a small rule-based stand-in
(`_FallbackLLM`) so the whole graph is still runnable end-to-end without any
API key -- useful for wiring/testing the orchestrator's plumbing before you
have a key, or in CI. It is NOT a substitute for real language understanding:
swap in a real key as soon as you can for anything beyond a smoke test.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from .config import settings
from .logging_config import get_logger

logger = get_logger(__name__)


def _extract_json(text: str) -> Optional[dict]:
    """Best-effort JSON extraction from an LLM response (handles ```json
    fences and stray prose around the object)."""
    text = text.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fence_match.group(1) if fence_match else text
    if not fence_match:
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            candidate = brace_match.group(0)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        logger.warning("Could not parse JSON from LLM response: %s", text[:200])
        return None


class _FallbackLLM:
    """Rule-based stand-in used only when no GROQ_API_KEY is configured."""

    _KEYWORD_TOOLS = {
        "rain": "prediction_tool", "rainfall": "prediction_tool", "flood": "prediction_tool",
        "forecast": "weather_tool", "weather": "weather_tool", "temperature": "weather_tool",
        "alert": "alert_tool", "warning": "alert_tool", "danger": "alert_tool",
        "landslide": "digital_twin_tool", "hazard": "digital_twin_tool", "simulation": "digital_twin_tool",
        "data": "data_tool", "dataset": "data_tool", "history": "data_tool",
        "research": "rag_tool", "paper": "rag_tool", "document": "rag_tool", "guideline": "rag_tool",
        "notify": "notification_tool", "sms": "notification_tool", "email": "notification_tool",
    }

    def chat_json(self, system: str, user: str) -> Dict[str, Any]:
        lowered = user.lower()
        if "intent" in system.lower():
            tools = sorted({t for kw, t in self._KEYWORD_TOOLS.items() if kw in lowered}) or ["weather_tool"]
            return {
                "intent": "weather_query",
                "entities": {"raw_query": user},
                "requires_tools": tools,
            }
        # task planning fallback: one call per required tool, no params inference
        tools = sorted({t for kw, t in self._KEYWORD_TOOLS.items() if kw in lowered}) or ["weather_tool"]
        return {"tasks": [{"tool": t, "params": {"query": user}} for t in tools]}

    def chat_text(self, system: str, user: str) -> str:
        return (
            "[fallback LLM -- no GROQ_API_KEY configured, this is a placeholder response] "
            "Based on the available data: " + user
        )


class LLMClient:
    def __init__(self):
        if settings.has_llm_key:
            from langchain_groq import ChatGroq
            self._chat = ChatGroq(model=settings.groq_model, api_key=settings.groq_api_key, temperature=0.2)
            self._fallback = None
        else:
            logger.warning(
                "GROQ_API_KEY not set -- using rule-based fallback LLM. "
                "Set GROQ_API_KEY for real intent understanding / response generation."
            )
            self._chat = None
            self._fallback = _FallbackLLM()

    def chat_json(self, system: str, user: str) -> Dict[str, Any]:
        """Call the LLM expecting a JSON object back; returns {} on failure."""
        if self._fallback is not None:
            return self._fallback.chat_json(system, user)

        from langchain_core.messages import HumanMessage, SystemMessage
        messages: List[Any] = [SystemMessage(content=system), HumanMessage(content=user)]
        result = self._chat.invoke(messages)
        parsed = _extract_json(result.content)
        return parsed or {}

    def chat_text(self, system: str, user: str) -> str:
        if self._fallback is not None:
            return self._fallback.chat_text(system, user)

        from langchain_core.messages import HumanMessage, SystemMessage
        messages: List[Any] = [SystemMessage(content=system), HumanMessage(content=user)]
        result = self._chat.invoke(messages)
        return result.content


llm_client = LLMClient()
