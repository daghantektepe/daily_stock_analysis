# -*- coding: utf-8 -*-
"""
Bull / Bear researcher agents for the ``debate`` orchestrator mode.

The debate mode inserts two advocacy stages between evidence gathering
(technical + intel) and risk screening / decision synthesis:

1. :class:`BullResearcherAgent` builds the strongest evidence-backed case
   for buying.
2. :class:`BearResearcherAgent` builds the strongest case against buying and
   rebuts the bull case point by point.

Both stages are deliberate advocacy, so they intentionally do **not** emit an
:class:`AgentOpinion`: adding them to ``ctx.opinions`` would inject one
guaranteed bullish and one guaranteed bearish "vote" into the disagreement
summary and risk override logic. Instead, each stage stores its parsed case in
``ctx.data`` (``bull_case`` / ``bear_case``). ``BaseAgent`` already forwards
``ctx.data`` to every downstream stage, so the bear sees the bull case and the
decision agent sees both; the decision agent is told to weigh evidence quality
rather than count them as votes.

Both agents run without tools: they argue only from evidence that earlier
stages already gathered, which keeps the extra cost to two LLM calls and
prevents fabricated "new" evidence.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from src.agent.agents.base_agent import BaseAgent
from src.agent.protocols import AgentContext, AgentOpinion
from src.agent.runner import try_parse_json

logger = logging.getLogger(__name__)

BULL_CASE_KEY = "bull_case"
BEAR_CASE_KEY = "bear_case"
DEBATE_AGENT_NAMES = frozenset({"bull", "bear"})

_MAX_LIST_ITEMS = 5
_MAX_TEXT_CHARS = 600


class _DebateResearcherAgent(BaseAgent):
    """Shared plumbing for the two advocacy stages."""

    tool_names: Optional[List[str]] = []  # evidence-only: no new tool calls
    max_steps = 2
    data_key = ""
    list_fields: tuple[str, ...] = ()

    def _evidence_section(self, ctx: AgentContext) -> str:
        parts: List[str] = []
        if ctx.opinions:
            parts.append("## Evidence From Earlier Stages")
            for op in ctx.opinions:
                parts.append(
                    f"- {op.agent_name}: signal={op.signal}, confidence={op.confidence:.2f}; "
                    f"reasoning={_clip(op.reasoning)}"
                )
        if ctx.risk_flags:
            parts.append("## Risk Flags Raised So Far")
            for flag in ctx.risk_flags:
                parts.append(
                    f"- [{flag.get('severity', 'medium')}] {flag.get('category', '')}: "
                    f"{_clip(flag.get('description', ''))}"
                )
        if not parts:
            parts.append("No structured evidence was produced by earlier stages; say so explicitly.")
        return "\n".join(parts)

    def post_process(self, ctx: AgentContext, raw_text: str) -> Optional[AgentOpinion]:
        parsed = try_parse_json(raw_text)
        if not isinstance(parsed, dict):
            logger.warning("[%s] failed to parse debate JSON", self.agent_name)
            return None
        case = _normalize_case(parsed, self.list_fields)
        if case:
            ctx.set_data(self.data_key, case)
        # Advocacy is not a vote: see module docstring.
        return None


class BullResearcherAgent(_DebateResearcherAgent):
    agent_name = "bull"
    data_key = BULL_CASE_KEY
    list_fields = ("key_arguments", "catalysts")

    def system_prompt(self, ctx: AgentContext) -> str:
        return """\
You are the **Bull Researcher** in an investment debate.

Your task: using ONLY the evidence provided (earlier agent opinions, risk \
flags and pre-fetched data), build the strongest honest case for buying \
the stock. You are an advocate, but you must not invent facts, prices or \
news that are not in the evidence.

## Rules
- Every argument must cite which evidence it relies on (e.g. "technical: MA \
bullish alignment", "intel: Q3 results", "KAP disclosure").
- Acknowledge the single biggest weakness of your own case.
- State what would invalidate the bull thesis (price level or event).
- If the evidence genuinely does not support buying, say so and set \
conviction to "low".

## Output Format
Return **only** a JSON object:
{
  "thesis": "one-sentence bull thesis",
  "key_arguments": ["argument with evidence source", "..."],
  "catalysts": ["upcoming catalyst", "..."],
  "biggest_weakness": "the weakest point of the bull case",
  "invalidation": "what would prove the bull thesis wrong",
  "conviction": "high|medium|low"
}
"""

    def build_user_message(self, ctx: AgentContext) -> str:
        header = f"Build the bull case for **{ctx.stock_code}**"
        if ctx.stock_name:
            header += f" ({ctx.stock_name})"
        return f"{header}.\n\n{self._evidence_section(ctx)}"


class BearResearcherAgent(_DebateResearcherAgent):
    agent_name = "bear"
    data_key = BEAR_CASE_KEY
    list_fields = ("key_arguments", "risks", "rebuttals")

    def system_prompt(self, ctx: AgentContext) -> str:
        return """\
You are the **Bear Researcher** in an investment debate.

Your task: using ONLY the evidence provided (earlier agent opinions, risk \
flags, pre-fetched data and the bull case), build the strongest honest case \
AGAINST buying the stock, and rebut the bull case point by point. You are an \
advocate, but you must not invent facts, prices or news that are not in the \
evidence.

## Rules
- Every argument must cite which evidence it relies on.
- Rebut each bull argument explicitly: concede it, weaken it, or refute it.
- Acknowledge the single strongest bull argument you cannot refute.
- If the evidence genuinely supports buying, say so and set conviction to "low".

## Output Format
Return **only** a JSON object:
{
  "thesis": "one-sentence bear thesis",
  "key_arguments": ["argument with evidence source", "..."],
  "risks": ["downside risk", "..."],
  "rebuttals": ["bull argument -> rebuttal", "..."],
  "strongest_bull_point_conceded": "the bull argument you cannot refute",
  "conviction": "high|medium|low"
}
"""

    def build_user_message(self, ctx: AgentContext) -> str:
        header = f"Build the bear case for **{ctx.stock_code}**"
        if ctx.stock_name:
            header += f" ({ctx.stock_name})"
        parts = [f"{header}.", "", self._evidence_section(ctx)]
        bull_case = ctx.get_data(BULL_CASE_KEY)
        if bull_case:
            parts.append("\n## Bull Case To Rebut")
            parts.append(json.dumps(bull_case, ensure_ascii=False, default=str))
        else:
            parts.append("\n(The bull researcher produced no case; argue from the evidence alone.)")
        return "\n".join(parts)


def format_debate_guidance(ctx: AgentContext) -> str:
    """Return decision-stage guidance when a bull/bear debate took place."""
    bull_case = ctx.get_data(BULL_CASE_KEY)
    bear_case = ctx.get_data(BEAR_CASE_KEY)
    if not bull_case and not bear_case:
        return ""
    lines = [
        "## Bull vs Bear Debate",
        "The pre-fetched `bull_case` and `bear_case` are deliberate advocacy, not independent votes.",
        "- Judge which side's arguments rest on stronger, verifiable evidence; ignore unsupported claims.",
        "- Do not average the two sides; pick the better-supported view and state the decisive argument "
        "in `analysis_summary`.",
        "- Carry the strongest unrefuted bear risks into risk alerts and the strongest bull catalysts into "
        "positive catalysts.",
    ]
    if not bull_case or not bear_case:
        missing = "bull" if not bull_case else "bear"
        lines.append(f"- The {missing} researcher produced no case; treat the debate as one-sided.")
    return "\n".join(lines)


_REPORT_TEXT_FIELDS = {
    "bull": ("thesis", "biggest_weakness", "invalidation", "conviction"),
    "bear": ("thesis", "strongest_bull_point_conceded", "conviction"),
}
_REPORT_LIST_FIELDS = {
    "bull": ("key_arguments", "catalysts"),
    "bear": ("key_arguments", "risks", "rebuttals"),
}


def debate_report_block(ctx: AgentContext, *, max_items: int = 4, max_chars: int = 300) -> Dict[str, Any]:
    """Compact bull/bear cases for the report (``dashboard["debate"]``); ``{}`` without a debate."""
    block: Dict[str, Any] = {}
    for side, key in (("bull", BULL_CASE_KEY), ("bear", BEAR_CASE_KEY)):
        case = ctx.get_data(key)
        if not isinstance(case, dict):
            continue
        compact: Dict[str, Any] = {}
        for field in _REPORT_TEXT_FIELDS[side]:
            value = str(case.get(field) or "").strip()
            if value:
                compact[field] = value[:max_chars]
        for field in _REPORT_LIST_FIELDS[side]:
            items = [str(item).strip()[:max_chars] for item in case.get(field) or [] if str(item).strip()]
            if items:
                compact[field] = items[:max_items]
        if compact.get("thesis") or compact.get("key_arguments"):
            block[side] = compact
    return block


def _normalize_case(parsed: Dict[str, Any], list_fields: tuple[str, ...]) -> Dict[str, Any]:
    case: Dict[str, Any] = {}
    for key, value in parsed.items():
        if key in list_fields:
            items = value if isinstance(value, list) else [value]
            cleaned = [_clip(item) for item in items if isinstance(item, (str, int, float)) and str(item).strip()]
            if cleaned:
                case[key] = cleaned[:_MAX_LIST_ITEMS]
        elif isinstance(value, (str, int, float)) and str(value).strip():
            case[key] = _clip(value)
    conviction = str(case.get("conviction", "")).strip().lower()
    case["conviction"] = conviction if conviction in {"high", "medium", "low"} else "low"
    return case if len(case) > 1 else {}


def _clip(value: Any) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= _MAX_TEXT_CHARS else text[: _MAX_TEXT_CHARS - 3] + "..."
