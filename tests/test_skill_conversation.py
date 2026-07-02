"""多轮会话测试：真实 LLM 路由 + SkillConversationSession 端到端。"""

from __future__ import annotations

from pathlib import Path
import os

import pytest
from openai import APIStatusError, RateLimitError

from _skill import (
    CallableSkillAdapter,
    FileSkillDiscovery,
    MatchResult,
    RedLineViolation,
)
from agent.conversation import SkillConversationSession
from llm.skill_router import LLMRouterResponseError, OpenAIChatSkillRouter, load_skill_env
from llm.schema import LLMDecisionSchemaError
from tests.skill_fixtures import build_pipeline_test_skills

load_skill_env()

LLM_MARK = pytest.mark.skipif(
    not (os.environ.get("API_KEY") or os.environ.get("OPENAI_API_KEY")),
    reason="需要 API_KEY",
)


def _make_adapter():
    return CallableSkillAdapter("conversation-adapter", lambda p, s, c: f"executed:{s.name}")


def _safe_handle(session, query, adapter, fields=None):
    try:
        return session.handle(query, adapter=adapter, fields=fields)
    except (RateLimitError, APIStatusError) as exc:
        status = getattr(exc, "status_code", 0)
        if status in {401, 403, 429, 503}:
            pytest.skip(f"供应商不可用({status})")
        raise
    except LLMRouterResponseError as exc:
        raw = exc.raw_response.lower()
        if any(w in raw for w in ("quota", "rate", "limit", "recharge", "topup")):
            pytest.skip("额度不足")
        raise
    except LLMDecisionSchemaError:
        pytest.skip("LLM 返回不符合 schema 的 JSON（非确定性行为）")


# ---------------------------------------------------------------------------
# 真实 LLM 多轮
# ---------------------------------------------------------------------------

@LLM_MARK
def test_conversation_redline_block_then_fill_and_execute(tmp_path: Path) -> None:
    """第一轮缺字段被拦 → 第二轮补字段 → 执行成功。"""
    index = FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()
    session = SkillConversationSession(OpenAIChatSkillRouter(index))
    adapter = _make_adapter()

    # 第一轮：缺所有字段
    r1 = _safe_handle(session, "帮我做安全审查", adapter)
    assert isinstance(r1.activation, RedLineViolation)
    assert r1.activation.skill.name == "security-auditor"
    assert session.state.pending_skill_name == "security-auditor"

    # 第二轮：补全字段
    r2 = _safe_handle(
        session,
        "审查范围 ./src，语言 python，输出 json 格式",
        adapter,
        fields={"scope": "./src", "language": "python", "output_format": "json"},
    )
    assert isinstance(r2.activation, MatchResult)
    assert r2.execution is not None
    assert r2.execution.output == "executed:security-auditor"
    assert session.state.pending_skill_name is None


@LLM_MARK
def test_conversation_three_round_fill(tmp_path: Path) -> None:
    """三字段分三轮逐轮补全。"""
    index = FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()
    session = SkillConversationSession(OpenAIChatSkillRouter(index))
    adapter = _make_adapter()

    # 第一轮：触发 security-auditor，缺所有字段
    r1 = _safe_handle(session, "做安全审查", adapter)
    assert isinstance(r1.activation, RedLineViolation)
    assert session.state.pending_skill_name == "security-auditor"

    # 第二轮：补 scope
    r2 = _safe_handle(session, "审查范围是 ./src", adapter, fields={"scope": "./src"})
    assert isinstance(r2.activation, RedLineViolation)
    assert len(session.state.missing_fields) >= 1

    # 第三轮：补 language 和 output_format
    r3 = _safe_handle(
        session, "语言是 python，输出 json",
        adapter,
        fields={"language": "python", "output_format": "json"},
    )
    assert isinstance(r3.activation, MatchResult)
    assert r3.execution is not None
    assert session.state.pending_skill_name is None


@LLM_MARK
def test_conversation_state_resets_after_completion(tmp_path: Path) -> None:
    """执行完成后 pending 状态应被清空。"""
    index = FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()
    session = SkillConversationSession(OpenAIChatSkillRouter(index))
    adapter = _make_adapter()

    r1 = _safe_handle(
        session,
        "审查 ./src 的 python 代码，输出 json",
        adapter,
        fields={"scope": "./src", "language": "python", "output_format": "json"},
    )
    assert isinstance(r1.activation, MatchResult)
    assert r1.execution is not None
    assert session.state.pending_skill_name is None
    assert session.state.missing_fields == ()


@LLM_MARK
def test_conversation_independent_calls_no_state_leak(tmp_path: Path) -> None:
    """多次独立调用不应互相污染状态。"""
    index = FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()
    session = SkillConversationSession(OpenAIChatSkillRouter(index))
    adapter = _make_adapter()

    # 第一次：echo
    r1 = _safe_handle(session, "echo test", adapter)
    assert isinstance(r1.activation, MatchResult)
    assert r1.activation.skill.name == "simple-echo"
    assert session.state.pending_skill_name is None

    # 第二次：echo 再次
    r2 = _safe_handle(session, "echo another test", adapter)
    assert isinstance(r2.activation, MatchResult)
    assert r2.activation.skill.name == "simple-echo"
    assert session.state.pending_skill_name is None


@LLM_MARK
def test_conversation_handles_unrelated_query_during_pending(tmp_path: Path) -> None:
    """pending 期间发无关请求，状态不变。"""
    index = FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()
    session = SkillConversationSession(OpenAIChatSkillRouter(index))
    adapter = _make_adapter()

    # 先触发安全审查拦截
    r1 = _safe_handle(session, "做安全审查", adapter)
    assert isinstance(r1.activation, RedLineViolation)
    assert session.state.pending_skill_name == "security-auditor"

    # 发一个无关请求
    r2 = _safe_handle(session, "今天天气怎么样", adapter)
    # pending skill 保持不变
    assert session.state.pending_skill_name == "security-auditor"

    # 后续补全并执行
    r3 = _safe_handle(
        session, "scope=./src language=python output_format=json",
        adapter,
        fields={"scope": "./src", "language": "python", "output_format": "json"},
    )
    assert isinstance(r3.activation, MatchResult)
    assert r3.execution is not None
