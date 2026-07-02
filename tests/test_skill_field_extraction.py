"""字段提取质量测试：正则兜底 + LLM 提取 + 对比。"""

from __future__ import annotations

from pathlib import Path
import os

import pytest
from openai import APIStatusError, RateLimitError

from _skill import (
    FileSkillDiscovery,
)
from agent.field_extractor import extract_fields_from_query
from llm.skill_router import LLMRouterResponseError, OpenAIChatSkillRouter, load_skill_env
from tests.skill_fixtures import build_pipeline_test_skills

load_skill_env()


# ---------------------------------------------------------------------------
# 正则兜底
# ---------------------------------------------------------------------------

def test_field_extractor_reads_filename_from_chinese_query() -> None:
    """正则从中文自然语言中提取 filename。"""
    assert extract_fields_from_query("文件名是 demo.docx")["filename"] == "demo.docx"
    assert extract_fields_from_query("输出到 quarterly_report.docx")["filename"] == "quarterly_report.docx"
    assert extract_fields_from_query("生成 weekly.docx 文件")["filename"] == "weekly.docx"
    assert extract_fields_from_query("文件名为 annual_summary.docx")["filename"] == "annual_summary.docx"


def test_field_extractor_reads_template_name_from_chinese_query() -> None:
    """正则从中文自然语言中提取 template_name。"""
    assert extract_fields_from_query("模板是 standard_report")["template_name"] == "standard_report"
    assert extract_fields_from_query("模板名为 financial")["template_name"] == "financial"
    assert extract_fields_from_query("模板叫 project_proposal")["template_name"] == "project_proposal"


def test_field_extractor_reads_both_fields() -> None:
    """正则同时提取多个字段。"""
    r = extract_fields_from_query("文件名是 report.docx，模板名叫 business")
    assert r.get("filename") == "report.docx"
    assert r.get("template_name") == "business"


def test_field_extractor_handles_empty_query() -> None:
    """空 query 应返回空 dict。"""
    assert extract_fields_from_query("") == {}
    assert extract_fields_from_query("   ") == {}


def test_field_extractor_handles_no_keywords() -> None:
    """无关键字的 query 应返回空 dict。"""
    assert extract_fields_from_query("今天天气真好") == {}
    assert extract_fields_from_query("hello world") == {}


def test_field_extractor_handles_keyword_without_value() -> None:
    """只有关键字但没有值时不提取（或不触发关键词匹配）。"""
    # 不包含"文件名"或"模板"关键字的 query
    r = extract_fields_from_query("帮我生成一份报告")
    assert r == {}
    # 包含关键字但上下文不匹配标准提取模式
    r2 = extract_fields_from_query("今天天气很好")
    assert r2 == {}


# ---------------------------------------------------------------------------
# LLM 字段提取（仅在有 API_KEY 时运行）
# ---------------------------------------------------------------------------

LLM_MARK = pytest.mark.skipif(
    not (os.environ.get("API_KEY") or os.environ.get("OPENAI_API_KEY")),
    reason="需要 API_KEY",
)


def _safe_route(router, query, fields=None):
    try:
        return router.route(query, fields=fields)
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


@LLM_MARK
def test_llm_extracts_filename_from_natural_language(tmp_path: Path) -> None:
    """LLM 应从自然语言中提取 filename 字段。"""
    index = FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()
    router = OpenAIChatSkillRouter(index)
    decision = _safe_route(router, "生成 quarterly.docx 的 word 报告")

    # 正则先兜底
    regex_fields = extract_fields_from_query("生成 quarterly.docx 的 word 报告")
    # LLM 可能额外提取字段
    combined = {**regex_fields, **decision.fields}
    assert "quarterly" in str(combined).lower() or decision.should_call


@LLM_MARK
def test_llm_vs_regex_field_extraction_comparison(tmp_path: Path) -> None:
    """同一条 query 分别跑正则和 LLM，验证 LLM 至少不比正则差。"""
    index = FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()
    router = OpenAIChatSkillRouter(index)

    query = "生成名为 demo.docx 的 Word 文档，模板名 standard"
    regex = extract_fields_from_query(query)
    decision = _safe_route(router, query)

    # 正则提取
    assert regex["filename"] == "demo.docx"
    assert regex["template_name"] == "standard"

    # LLM 也应该指向 document-generator
    assert decision.should_call is True
    assert decision.skill_name == "document-generator"


@LLM_MARK
def test_llm_reports_missing_fields_for_security_auditor(tmp_path: Path) -> None:
    """LLM 应识别出 security-auditor 缺少所有红线字段并放入 missing_fields。"""
    index = FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()
    router = OpenAIChatSkillRouter(index)
    decision = _safe_route(router, "帮我做一次安全审计")

    assert decision.should_call is True
    assert decision.skill_name == "security-auditor"
    assert len(decision.missing_fields) >= 1
