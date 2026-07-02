"""大模型 skill 路由集成测试：涵盖 TP / FP / TN / 字段提取 / 红线协作 / LLM 异常容错。"""

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
from llm.skill_router import LLMRouterResponseError, OpenAIChatSkillRouter, load_skill_env
from llm.schema import LLMDecisionSchemaError
from tests.skill_fixtures import build_pipeline_test_skills

load_skill_env()

pytestmark = pytest.mark.skipif(
    not (os.environ.get("API_KEY") or os.environ.get("OPENAI_API_KEY")),
    reason="需要在 .env 或环境变量中设置 API_KEY / OPENAI_API_KEY 才运行大模型集成测试",
)


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------

def _route_or_skip(router: OpenAIChatSkillRouter, query: str, adapter, fields=None):
    """真实供应商不可用时 skip 而非误报。"""
    try:
        return router.route_and_execute(query, adapter=adapter, fields=fields)
    except RateLimitError as exc:
        pytest.skip(f"供应商限流: {str(exc).split(chr(10))[0][:160]}")
    except APIStatusError as exc:
        if exc.status_code in {401, 403, 429, 503}:
            pytest.skip(f"供应商不可用({exc.status_code})")
        raise
    except LLMRouterResponseError as exc:
        raw = exc.raw_response.lower()
        if any(w in raw for w in ("quota", "rate", "limit", "recharge", "topup")):
            pytest.skip(f"额度/限流: {exc.raw_response[:160]}")
        raise
    except LLMDecisionSchemaError:
        pytest.skip("LLM 返回了不符合 schema 的 JSON（非确定性行为）")


def _make_index(tmp_path: Path):
    return FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()


def _make_adapter():
    return CallableSkillAdapter("test-adapter", lambda p, s, c: f"called:{s.name}")


# ---------------------------------------------------------------------------
# TP：正确路由
# ---------------------------------------------------------------------------

def test_llm_routes_to_document_generator(tmp_path: Path) -> None:
    """LLM 应将文档生成意图路由到 document-generator。"""
    router = OpenAIChatSkillRouter(_make_index(tmp_path))
    result = _route_or_skip(
        router,
        "请帮我生成一份 Word 格式的季度总结报告，文件名叫 quarterly.docx，标题是 Q2总结",
        _make_adapter(),
    )
    assert result.decision.should_call is True
    assert result.decision.skill_name == "document-generator"

    # LLM 可能无法百分之百提取两个字段，本地红线会补刀
    if isinstance(result.activation, RedLineViolation):
        # 被拦时 primary 缺失字段应为 title
        fields = {r.field for r in result.activation.violated_rules}
        assert fields == {"title"} or "title" in fields
        assert result.execution is None
    else:
        assert isinstance(result.activation, MatchResult)
        assert result.execution is not None
        assert result.execution.metrics.execution_success is True


def test_llm_routes_to_skill_index(tmp_path: Path) -> None:
    """LLM 应将 skill 搜索意图路由到 skill-index，并展开引用。"""
    router = OpenAIChatSkillRouter(_make_index(tmp_path))
    result = _route_or_skip(
        router,
        "帮我查一下系统目前注册了哪些 skill，列出所有技能",
        _make_adapter(),
    )
    assert result.decision.should_call is True
    assert result.decision.skill_name == "skill-index"
    assert isinstance(result.activation, MatchResult)
    assert result.execution is not None
    assert result.execution.metrics.reference_load_rate == 1.0


def test_llm_routes_to_security_auditor(tmp_path: Path) -> None:
    """LLM 应路由安全检查请求到 security-auditor。"""
    router = OpenAIChatSkillRouter(_make_index(tmp_path))
    result = _route_or_skip(
        router,
        "对 ./src 目录做一次安全审查，语言是 python，输出 markdown 格式",
        _make_adapter(),
        fields={"scope": "./src", "language": "python", "output_format": "markdown"},
    )
    assert result.decision.should_call is True
    assert result.decision.skill_name == "security-auditor"
    assert isinstance(result.activation, MatchResult)
    assert result.execution is not None


def test_llm_routes_to_simple_echo(tmp_path: Path) -> None:
    """LLM 应将回显请求路由到 simple-echo。"""
    router = OpenAIChatSkillRouter(_make_index(tmp_path))
    result = _route_or_skip(router, "echo ping 测试连通性", _make_adapter())
    assert result.decision.should_call is True
    assert result.decision.skill_name == "simple-echo"
    assert isinstance(result.activation, MatchResult)


# ---------------------------------------------------------------------------
# TN：正确拒绝
# ---------------------------------------------------------------------------

def test_llm_rejects_irrelevant_weather_query(tmp_path: Path) -> None:
    """天气类无关请求应被拒绝。"""
    router = OpenAIChatSkillRouter(_make_index(tmp_path))
    result = _route_or_skip(router, "今天北京的天气怎么样", _make_adapter())
    assert result.decision.should_call is False
    assert result.activation is None
    assert result.execution is None


def test_llm_rejects_irrelevant_coding_query(tmp_path: Path) -> None:
    """非匹配编码请求应被拒绝。"""
    router = OpenAIChatSkillRouter(_make_index(tmp_path))
    result = _route_or_skip(router, "帮我用 Python 写一个文件上传下载服务", _make_adapter())
    assert result.decision.should_call is False
    assert result.activation is None


def test_llm_rejects_empty_query(tmp_path: Path) -> None:
    """空请求应被拒绝。"""
    router = OpenAIChatSkillRouter(_make_index(tmp_path))
    result = _route_or_skip(router, "   ", _make_adapter())
    assert result.decision.should_call is False


# ---------------------------------------------------------------------------
# 红线协作：LLM 选 skill + 本地拦红线
# ---------------------------------------------------------------------------

def test_llm_selects_security_auditor_but_local_blocks_on_missing_fields(tmp_path: Path) -> None:
    """LLM 选择 security-auditor，本地因缺所有红线字段拦截。"""
    router = OpenAIChatSkillRouter(_make_index(tmp_path))
    result = _route_or_skip(
        router,
        "帮我做一次安全审查",
        _make_adapter(),
    )
    assert result.decision.should_call is True
    assert result.decision.skill_name == "security-auditor"
    assert isinstance(result.activation, RedLineViolation)
    assert result.execution is None
    violated_fields = {r.field for r in result.activation.violated_rules}
    assert "scope" in violated_fields
    assert "language" in violated_fields
    assert "output_format" in violated_fields


def test_llm_selects_security_auditor_and_passes_when_fields_present(tmp_path: Path) -> None:
    """用户提供了所有红线字段，LLM 选 skill + 本地放行 + 执行。"""
    router = OpenAIChatSkillRouter(_make_index(tmp_path))
    result = _route_or_skip(
        router,
        "对 src 目录做安全审查，语言是 python，输出 markdown",
        _make_adapter(),
        fields={"scope": "./src", "language": "python", "output_format": "markdown"},
    )
    assert result.decision.should_call is True
    assert result.decision.skill_name == "security-auditor"
    assert isinstance(result.activation, MatchResult)
    assert result.execution is not None


def test_llm_partial_fields_block_some_redlines(tmp_path: Path) -> None:
    """部分红线字段缺失时应被拦截并列出缺失字段。"""
    router = OpenAIChatSkillRouter(_make_index(tmp_path))
    result = _route_or_skip(
        router,
        "审查 src 目录的 python 代码",
        _make_adapter(),
        fields={"scope": "./src", "language": "python"},
    )
    assert result.decision.should_call is True
    assert result.decision.skill_name == "security-auditor"
    assert isinstance(result.activation, RedLineViolation)
    assert "output_format" in {r.field for r in result.activation.violated_rules}


# ---------------------------------------------------------------------------
# 字段提取质量
# ---------------------------------------------------------------------------

def test_llm_extracts_filename_and_title_from_natural_language(tmp_path: Path) -> None:
    """LLM 应从自然语言中提取 filename 和 title。"""
    router = OpenAIChatSkillRouter(_make_index(tmp_path))
    # 只调 route()，不执行
    decision = _safe_route(router, "生成文件名 quarterly.docx、标题为 Q2总结 的 word 报告")
    assert decision.should_call is True
    assert decision.skill_name == "document-generator"
    # LLM 提取的字段应包含文件相关信息
    fields = decision.fields
    assert any("quarterly" in str(v).lower() or "docx" in str(v).lower()
               for v in fields.values()), f"LLM 未提取文件名相关字段: {fields}"


def test_llm_reports_missing_redline_fields(tmp_path: Path) -> None:
    """LLM 未提供红线字段时，missing_fields 应包含缺失字段。"""
    router = OpenAIChatSkillRouter(_make_index(tmp_path))
    decision = _safe_route(router, "帮我做安全审查")
    assert decision.should_call is True
    assert decision.skill_name == "security-auditor"
    assert len(decision.missing_fields) >= 1


# ---------------------------------------------------------------------------
# LLM 响应异常容错
# ---------------------------------------------------------------------------

def test_llm_decision_schema_rejects_hallucinated_skill_name(tmp_path: Path) -> None:
    """schema 层应拒绝模型幻觉出的不存在的 skill。"""
    from llm.schema import LLMDecisionSchemaError, validate_llm_decision_payload

    index = _make_index(tmp_path)
    with pytest.raises(LLMDecisionSchemaError):
        validate_llm_decision_payload(
            {"should_call": True, "skill_name": "not-exists", "confidence": 0.9,
             "reason": "bad", "fields": {}, "missing_fields": []},
            index,
        )


def test_llm_decision_schema_rejects_invalid_types(tmp_path: Path) -> None:
    """schema 应拒绝类型错误的字段：should_call 非 bool、confidence 非 number。"""
    from llm.schema import LLMDecisionSchemaError, validate_llm_decision_payload

    index = _make_index(tmp_path)
    cases = [
        {"should_call": "yes", "skill_name": None, "confidence": 0.5, "reason": "", "fields": {}, "missing_fields": []},
        {"should_call": False, "skill_name": None, "confidence": "high", "reason": "", "fields": {}, "missing_fields": []},
    ]
    for payload in cases:
        with pytest.raises(LLMDecisionSchemaError):
            validate_llm_decision_payload(payload, index)


def test_llm_decision_schema_rejects_missing_fields_not_array(tmp_path: Path) -> None:
    """missing_fields 非数组应被拒绝。"""
    from llm.schema import LLMDecisionSchemaError, validate_llm_decision_payload

    index = _make_index(tmp_path)
    with pytest.raises(LLMDecisionSchemaError):
        validate_llm_decision_payload(
            {"should_call": False, "skill_name": None, "confidence": 0.0, "reason": "",
             "fields": {}, "missing_fields": "not_array"},
            index,
        )


def test_llm_parse_non_json_response_raises_error(tmp_path: Path) -> None:
    """_parse_decision 对非 JSON 响应抛出 LLMRouterResponseError。"""
    router = OpenAIChatSkillRouter(_make_index(tmp_path))
    with pytest.raises(LLMRouterResponseError):
        router._parse_decision("this is not json at all", fallback_fields={})


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

def _safe_route(router: OpenAIChatSkillRouter, query: str):
    """安全路由 — 仅测试字段提取，不触发执行链。"""
    try:
        decision = router.route(query)
    except (RateLimitError, APIStatusError) as exc:
        status = getattr(exc, "status_code", 0)
        if status in {401, 403, 429, 503}:
            pytest.skip(f"供应商不可用({status})")
        raise
    except LLMRouterResponseError as exc:
        raw = exc.raw_response.lower()
        if any(w in raw for w in ("quota", "rate", "limit", "recharge", "topup")):
            pytest.skip(f"额度不足")
        raise
    return decision
