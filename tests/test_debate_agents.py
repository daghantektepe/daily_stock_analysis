# -*- coding: utf-8 -*-
"""Tests for the bull/bear debate orchestrator mode."""

import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    import litellm  # noqa: F401
except ModuleNotFoundError:
    sys.modules["litellm"] = MagicMock()

from src.agent.agents.debate_agents import (
    BEAR_CASE_KEY,
    BULL_CASE_KEY,
    BearResearcherAgent,
    BullResearcherAgent,
    format_debate_guidance,
)
from src.agent.agents.decision_agent import DecisionAgent
from src.agent.disagreement import build_agent_disagreement_summary
from src.agent.orchestrator import AgentOrchestrator
from src.agent.protocols import AgentContext, AgentOpinion, StageResult, StageStatus
from src.config import Config


def _ctx() -> AgentContext:
    ctx = AgentContext(query="analyze", stock_code="THYAO.IS", stock_name="Türk Hava Yolları")
    ctx.add_opinion(AgentOpinion(agent_name="technical", signal="buy", confidence=0.7, reasoning="MA bullish"))
    ctx.add_opinion(AgentOpinion(agent_name="intel", signal="hold", confidence=0.5, reasoning="Q3 results mixed"))
    ctx.add_risk_flag(category="valuation", description="PE above sector", severity="medium")
    return ctx


def _agents():
    kwargs = dict(tool_registry=MagicMock(), llm_adapter=MagicMock())
    return BullResearcherAgent(**kwargs), BearResearcherAgent(**kwargs)


def test_debate_mode_builds_bull_and_bear_before_risk_and_decision() -> None:
    orch = AgentOrchestrator(tool_registry=MagicMock(), llm_adapter=MagicMock(), mode="debate")
    names = [agent.agent_name for agent in orch._build_agent_chain(_ctx())]
    assert names == ["technical", "intel", "bull", "bear", "risk", "decision"]


def test_other_modes_do_not_include_debate_stages() -> None:
    for mode in ("quick", "standard", "full"):
        orch = AgentOrchestrator(tool_registry=MagicMock(), llm_adapter=MagicMock(), mode=mode)
        names = {agent.agent_name for agent in orch._build_agent_chain(_ctx())}
        assert not names & {"bull", "bear"}


def test_config_accepts_debate_mode() -> None:
    assert "debate" in Config._VALID_ORCHESTRATOR_MODES


def test_debate_agents_are_tool_free_and_non_critical() -> None:
    bull, bear = _agents()
    assert bull.tool_names == [] and bear.tool_names == []
    assert bull._filtered_registry().list_names() == []
    orch = AgentOrchestrator(tool_registry=MagicMock(), llm_adapter=MagicMock(), mode="debate")
    assert orch._is_non_critical_stage("bull") is True
    assert orch._is_non_critical_stage("bear") is True
    assert orch._is_non_critical_stage("technical") is False


def test_bull_case_is_stored_as_data_not_as_a_vote() -> None:
    bull, _ = _agents()
    ctx = _ctx()
    raw = json.dumps({
        "thesis": "Traffic growth and Q3 beat support upside",
        "key_arguments": ["technical: MA bullish alignment", "intel: Q3 results", "", 3],
        "catalysts": "LEAP-1B engine deal",
        "biggest_weakness": "Valuation above sector",
        "invalidation": "Close below 260 TRY",
        "conviction": "HIGH",
    })

    opinion = bull.post_process(ctx, raw)

    assert opinion is None
    case = ctx.get_data(BULL_CASE_KEY)
    assert case["thesis"].startswith("Traffic growth")
    assert case["key_arguments"] == ["technical: MA bullish alignment", "intel: Q3 results", "3"]
    assert case["catalysts"] == ["LEAP-1B engine deal"]
    assert case["conviction"] == "high"
    assert [op.agent_name for op in ctx.opinions] == ["technical", "intel"]


def test_unparseable_or_empty_case_is_ignored() -> None:
    bull, bear = _agents()
    ctx = _ctx()
    assert bull.post_process(ctx, "not json at all") is None
    assert bear.post_process(ctx, json.dumps({"conviction": "maybe"})) is None
    assert ctx.get_data(BULL_CASE_KEY) is None
    assert ctx.get_data(BEAR_CASE_KEY) is None


def test_bear_prompt_includes_evidence_and_bull_case() -> None:
    bull, bear = _agents()
    ctx = _ctx()
    no_bull = bear.build_user_message(ctx)
    assert "technical: signal=buy" in no_bull
    assert "PE above sector" in no_bull
    assert "produced no case" in no_bull

    ctx.set_data(BULL_CASE_KEY, {"thesis": "Upside", "conviction": "medium"})
    with_bull = bear.build_user_message(ctx)
    assert "## Bull Case To Rebut" in with_bull
    assert '"thesis": "Upside"' in with_bull
    assert "THYAO.IS" in bull.build_user_message(ctx)


def test_disagreement_summary_ignores_debate_cases() -> None:
    ctx = _ctx()
    ctx.set_data(BULL_CASE_KEY, {"thesis": "Upside", "conviction": "high"})
    ctx.set_data(BEAR_CASE_KEY, {"thesis": "Downside", "conviction": "high"})

    summary = build_agent_disagreement_summary(ctx)

    names = {
        item["agent_name"]
        for bucket in ("bullish_agents", "bearish_agents", "neutral_agents")
        for item in summary[bucket]
    }
    assert names == {"technical", "intel"}


def test_decision_prompt_gets_debate_guidance_only_when_debate_ran() -> None:
    decision = DecisionAgent(tool_registry=MagicMock(), llm_adapter=MagicMock())
    ctx = _ctx()
    assert format_debate_guidance(ctx) == ""
    assert "## Bull vs Bear Debate" not in decision.build_user_message(ctx)

    ctx.set_data(BULL_CASE_KEY, {"thesis": "Upside", "conviction": "high"})
    message = decision.build_user_message(ctx)
    assert "## Bull vs Bear Debate" in message
    assert "not independent votes" in message
    assert "The bear researcher produced no case" in message

    ctx.set_data(BEAR_CASE_KEY, {"thesis": "Downside", "conviction": "low"})
    assert "one-sided" not in format_debate_guidance(ctx)


def _stage(name, status=StageStatus.COMPLETED, error=None):
    result = StageResult(stage_name=name, status=status, error=error)
    result.meta["raw_text"] = "ok"
    result.meta["models_used"] = ["test/model"]
    return result


def test_pipeline_degrades_when_debate_stage_fails() -> None:
    orch = AgentOrchestrator(
        tool_registry=MagicMock(),
        llm_adapter=MagicMock(),
        mode="debate",
        config=SimpleNamespace(agent_risk_override=True),
    )
    ctx = _ctx()
    agents = []
    for name, status in (
        ("bull", StageStatus.FAILED),
        ("bear", StageStatus.COMPLETED),
        ("decision", StageStatus.COMPLETED),
    ):
        agent = MagicMock(agent_name=name)
        agent.run.return_value = _stage(name, status, error="llm down" if status == StageStatus.FAILED else None)
        agents.append(agent)

    with patch.object(orch, "_build_agent_chain", return_value=agents):
        result = orch._execute_pipeline(ctx, parse_dashboard=False)

    assert result.success is True
    for agent in agents:
        agent.run.assert_called_once()
    degraded = [item.get("stage") or item.get("stage_name") for item in ctx.meta.get("degraded_stages", [])]
    assert "bull" in degraded


def _debate_ctx() -> AgentContext:
    ctx = AgentContext(query="analyze", stock_code="ASELS.IS", stock_name="Aselsan")
    ctx.set_data("bull_case", {
        "thesis": "1,1 milyar USD ihracat sözleşmesi büyümeyi destekliyor",
        "key_arguments": ["KAP: 1,1 milyar USD sözleşme", "technical: MA bullish"],
        "catalysts": ["yeni ihracat sözleşmeleri"],
        "biggest_weakness": "yabancı satışı",
        "invalidation": "344 TL altı kapanış",
        "conviction": "medium",
    })
    ctx.set_data("bear_case", {
        "thesis": "değerleme pahalı",
        "key_arguments": ["intel: BofA satış listesi (tek kaynak)"],
        "risks": ["pay dönüşümü sonrası satış"],
        "rebuttals": ["sözleşme -> zaten fiyatlandı"],
        "strongest_bull_point_conceded": "sözleşme büyüklüğü",
        "conviction": "low",
    })
    return ctx


def test_debate_report_block_is_compact_and_empty_without_debate() -> None:
    from src.agent.agents.debate_agents import debate_report_block

    block = debate_report_block(_debate_ctx())
    assert block["bull"]["thesis"].startswith("1,1 milyar USD")
    assert block["bull"]["catalysts"] == ["yeni ihracat sözleşmeleri"]
    assert block["bear"]["strongest_bull_point_conceded"] == "sözleşme büyüklüğü"
    assert debate_report_block(AgentContext(query="q", stock_code="X")) == {}


def test_finalize_dashboard_attaches_debate_and_drops_forged_one() -> None:
    orch = AgentOrchestrator(tool_registry=MagicMock(), llm_adapter=MagicMock(), mode="debate")
    ctx = _debate_ctx()
    payload = {"decision_type": "hold", "dashboard": {"debate": {"bull": {"thesis": "forged"}}}}
    dashboard = orch._finalize_dashboard_payload(payload, ctx)
    assert dashboard["dashboard"]["debate"]["bull"]["thesis"].startswith("1,1 milyar USD")

    plain = AgentContext(query="analyze", stock_code="ASELS.IS")
    plain.set_data("news_context", "x")
    no_debate = orch._finalize_dashboard_payload(payload, plain)
    assert "debate" not in no_debate["dashboard"]


def test_report_renders_bull_bear_section_in_turkish() -> None:
    from src.agent.agents.debate_agents import debate_report_block
    from src.notification import _append_debate_block
    from src.report_language import get_report_labels

    lines = []
    _append_debate_block(lines, {"debate": debate_report_block(_debate_ctx())}, get_report_labels("tr"))
    text = "\n".join(lines)
    assert "### ⚖️ Boğa / Ayı Tartışması" in text
    assert "**🐂 Boğa tezi** (güven: orta): 1,1 milyar USD" in text
    assert "**🐻 Ayı tezi** (güven: düşük): değerleme pahalı" in text
    assert "- **Kabul edilen boğa argümanı**: sözleşme büyüklüğü" in text
    empty = []
    _append_debate_block(empty, {}, get_report_labels("tr"))
    assert empty == []
