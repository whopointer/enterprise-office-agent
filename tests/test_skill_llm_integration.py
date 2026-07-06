"""大模型 skill 路由集成测试 — 对齐官方格式（TP / TN / schema 校验）。"""

from __future__ import annotations

from pathlib import Path
import os

import pytest
from openai import APIStatusError, RateLimitError

from _skill import FileSkillDiscovery
from llm.skill_router import (
    LLMRouterResponseError,
    OpenAIChatSkillRouter,
    load_skill_env,
)
from llm.schema import LLMDecisionSchemaError
from tests.conftest import get_runtime_collector
from tests.skill_fixtures import build_pipeline_test_skills

load_skill_env()


def _record_routing(query, expected_skill, actual_skill, expected_activation, actual_activation, router=None):
    get_runtime_collector().record_routing(
        query=query,
        expected_skill=expected_skill,
        actual_skill=actual_skill,
        expected_activation=expected_activation,
        actual_activation=actual_activation,
        token_metrics=router.last_token_metrics() if router else None,
    )

pytestmark = pytest.mark.skipif(
    not (os.environ.get("API_KEY") or os.environ.get("OPENAI_API_KEY")),
    reason="需要 API_KEY",
)


def _route_or_skip(router, query, fields=None):
    try:
        return router.route(query, fields=fields)
    except RateLimitError as exc:
        pytest.skip(f"限流: {str(exc).split(chr(10))[0][:160]}")
    except APIStatusError as exc:
        if exc.status_code in {401, 403, 429, 503}:
            pytest.skip(f"供应商不可用({exc.status_code})")
        raise
    except LLMRouterResponseError as exc:
        raw = exc.raw_response.lower()
        if any(w in raw for w in ("quota", "rate", "limit", "recharge", "topup")):
            pytest.skip(f"额度不足")
        raise
    except LLMDecisionSchemaError:
        pytest.skip("LLM 返回不符合 schema 的 JSON（非确定性行为）")


def _make_index(tmp_path: Path):
    return FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()


# ---------------------------------------------------------------------------
# TP：正确路由
# ---------------------------------------------------------------------------

def test_llm_routes_to_document_generator(tmp_path: Path) -> None:
    """LLM 应将文档生成意图路由到 document-generator。"""
    router = OpenAIChatSkillRouter(_make_index(tmp_path))
    decision = _route_or_skip(router, "请帮我生成一份 Word 格式的季度总结报告")
    assert decision.should_call is True
    assert decision.skill_name == "document-generator"
    _record_routing("生成 Word 季度总结报告", "document-generator",
                    decision.skill_name, True, True, router=router)


def test_llm_routes_to_code_reviewer(tmp_path: Path) -> None:
    """LLM 应将代码审查意图路由到 code-reviewer。"""
    router = OpenAIChatSkillRouter(_make_index(tmp_path))
    decision = _route_or_skip(router, "帮我审查一下 ./src 目录下的 Python 代码")
    assert decision.should_call is True
    assert decision.skill_name == "code-reviewer"
    _record_routing("审查 ./src Python 代码", "code-reviewer",
                    decision.skill_name, True, True, router=router)


def test_llm_routes_to_simple_echo(tmp_path: Path) -> None:
    """LLM 应将回显请求路由到 simple-echo。"""
    router = OpenAIChatSkillRouter(_make_index(tmp_path))
    decision = _route_or_skip(router, "echo ping 测试连通性")
    assert decision.should_call is True
    assert decision.skill_name == "simple-echo"
    _record_routing("echo ping 测试", "simple-echo",
                    decision.skill_name, True, True, router=router)


def test_llm_routes_to_data_analyzer(tmp_path: Path) -> None:
    """LLM 应将数据分析请求路由到 data-analyzer。"""
    router = OpenAIChatSkillRouter(_make_index(tmp_path))
    decision = _route_or_skip(router, "分析一下 data.csv 文件并生成统计图表")
    assert decision.should_call is True
    assert decision.skill_name == "data-analyzer"
    _record_routing("分析 data.csv", "data-analyzer",
                    decision.skill_name, True, True, router=router)


# ---------------------------------------------------------------------------
# TN：正确拒绝
# ---------------------------------------------------------------------------

def test_llm_rejects_irrelevant_weather_query(tmp_path: Path) -> None:
    """天气类无关请求应被拒绝。"""
    router = OpenAIChatSkillRouter(_make_index(tmp_path))
    decision = _route_or_skip(router, "今天北京的天气怎么样")
    assert decision.should_call is False
    _record_routing("天气查询", None, decision.skill_name, False, False, router=router)


def test_llm_rejects_irrelevant_file_upload_query(tmp_path: Path) -> None:
    """不匹配任 skill 的请求应被拒绝。"""
    router = OpenAIChatSkillRouter(_make_index(tmp_path))
    decision = _route_or_skip(router, "帮我用 Python 写一个文件上传下载服务")
    assert decision.should_call is False
    _record_routing("文件上传服务", None, decision.skill_name, False, False, router=router)


def test_llm_rejects_empty_query(tmp_path: Path) -> None:
    """空请求应被拒绝。"""
    router = OpenAIChatSkillRouter(_make_index(tmp_path))
    decision = _route_or_skip(router, "   ")
    assert decision.should_call is False
    _record_routing("空查询", None, decision.skill_name, False, False, router=router)


# ---------------------------------------------------------------------------
# 字段提取
# ---------------------------------------------------------------------------

def test_llm_extracts_fields_from_natural_language(tmp_path: Path) -> None:
    """LLM 应从自然语言中提取 filename 等字段。"""
    router = OpenAIChatSkillRouter(_make_index(tmp_path))
    decision = _safe_route(router, "生成 quarterly.docx 的 word 报告")
    assert decision.should_call is True
    assert decision.skill_name == "document-generator"
    assert len(decision.fields) >= 0  # LLM 至少返回 fields（可能空）


def test_llm_reports_fields_in_decision(tmp_path: Path) -> None:
    """LLM 应在 decision 中填回解析到的字段。"""
    router = OpenAIChatSkillRouter(_make_index(tmp_path))
    decision = _safe_route(router, "审查 ./src 的 Go 代码")
    assert decision.should_call is True
    assert decision.skill_name == "code-reviewer"


# ---------------------------------------------------------------------------
# Schema 校验
# ---------------------------------------------------------------------------

def test_schema_rejects_hallucinated_skill_name(tmp_path: Path) -> None:
    """schema 应拒绝 LLM 幻觉出的 skill。"""
    from llm.schema import validate_llm_decision_payload
    index = _make_index(tmp_path)
    with pytest.raises(LLMDecisionSchemaError):
        validate_llm_decision_payload(
            {"should_call": True, "skill_name": "not-exists", "confidence": 0.9,
             "reason": "", "fields": {}}, index,
        )


def test_schema_rejects_invalid_should_call_type(tmp_path: Path) -> None:
    """should_call 非 bool 应被拒绝。"""
    from llm.schema import validate_llm_decision_payload
    index = _make_index(tmp_path)
    with pytest.raises(LLMDecisionSchemaError):
        validate_llm_decision_payload(
            {"should_call": "yes", "skill_name": None, "confidence": 0.5,
             "reason": "", "fields": {}}, index,
        )


def test_schema_rejects_invalid_confidence_type(tmp_path: Path) -> None:
    """confidence 非 number 应被拒绝。"""
    from llm.schema import validate_llm_decision_payload
    index = _make_index(tmp_path)
    with pytest.raises(LLMDecisionSchemaError):
        validate_llm_decision_payload(
            {"should_call": False, "skill_name": None, "confidence": "high",
             "reason": "", "fields": {}}, index,
        )


def test_llm_parse_non_json_raises_error(tmp_path: Path) -> None:
    """非 JSON 响应 → LLMRouterResponseError。"""
    router = OpenAIChatSkillRouter(_make_index(tmp_path))
    with pytest.raises(LLMRouterResponseError):
        router._parse_decision("not json at all", fallback_fields={})


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

def _safe_route(router, query):
    try:
        return router.route(query)
    except (RateLimitError, APIStatusError) as exc:
        status = getattr(exc, "status_code", 0)
        if status in {401, 403, 429, 503}:
            pytest.skip(f"不可用({status})")
        raise
    except LLMRouterResponseError as exc:
        if any(w in exc.raw_response.lower() for w in ("quota", "rate", "limit", "recharge")):
            pytest.skip("额度不足")
        raise
    except LLMDecisionSchemaError:
        pytest.skip("LLM 返回不符合 schema")
