"""所有适配器的真实执行链路测试。"""

from __future__ import annotations

from pathlib import Path
import os

import pytest

from _skill import (
    CallableSkillAdapter,
    FileSkillDiscovery,
    MatchResult,
    SkillExecutor,
)
from adapters.skill_adapters import (
    LangChainSkillAdapter,
    OpenAICompatibleSkillAdapter,
    SpringAIHttpAdapter,
    WordDocumentSkillAdapter,
)
from llm.skill_router import load_skill_env
from tests.skill_fixtures import build_pipeline_test_skills

load_skill_env()


def _make_index(tmp_path: Path):
    return FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()


def _make_match(index):
    return MatchResult(index.get("simple-echo"), 1.0, True, "direct")


# ---------------------------------------------------------------------------
# WordDocumentSkillAdapter — 真实 docx 生成
# ---------------------------------------------------------------------------

def test_word_document_adapter_generates_docx_artifact(tmp_path: Path) -> None:
    """WordDocument 适配器应在指定路径生成 .docx 文件。"""
    index = _make_index(tmp_path)
    output_path = tmp_path / "custom-report.docx"

    result = SkillExecutor(index, WordDocumentSkillAdapter()).execute(
        _make_match(index),
        user_query="生成报告",
        fields={"output_path": str(output_path), "title": "测试报告", "content": "测试内容"},
    )
    assert result.metrics.execution_success is True
    assert output_path.exists()
    assert str(output_path) in result.asset_paths


def test_word_document_adapter_uses_default_filename(tmp_path: Path) -> None:
    """不指定 output_path 时使用 skill-output.docx 作为默认文件名。"""
    index = _make_index(tmp_path)
    result = SkillExecutor(index, WordDocumentSkillAdapter()).execute(
        _make_match(index),
        user_query="生成报告",
        fields={"title": "默认文件名测试"},
    )
    assert result.metrics.execution_success is True
    assert result.asset_paths
    # 默认文件名：skill-output.docx（WordDocumentSkillAdapter 的硬编码兜底值）
    default_path = Path("skill-output.docx")
    assert default_path.exists(), f"期望 {default_path.resolve()} 存在但未找到"
    # 清理
    default_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# OpenAICompatibleSkillAdapter — 真实大模型调用
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not (os.environ.get("API_KEY") or os.environ.get("OPENAI_API_KEY")),
    reason="需要 API_KEY",
)
def test_openai_compatible_adapter_calls_real_llm(tmp_path: Path) -> None:
    """OpenAICompatibleSkillAdapter 应调用真实大模型并返回内容。"""
    index = _make_index(tmp_path)
    match = MatchResult(index.get("simple-echo"), 1.0, True, "direct")

    result = SkillExecutor(index, OpenAICompatibleSkillAdapter()).execute(
        match,
        user_query="回复: 你好",
    )
    assert result.metrics.execution_success is True
    assert len(str(result.output)) > 0


# ---------------------------------------------------------------------------
# LangChainSkillAdapter — 真实 callable 对象
# ---------------------------------------------------------------------------

class _RealInvokeRunner:
    """符合 LangChain Runnable 协议的最小可用对象。"""

    def invoke(self, payload: dict) -> str:
        return f"langchain-processed:{payload.get('skill', 'unknown')}"


def test_langchain_adapter_with_real_runnable(tmp_path: Path) -> None:
    """LangChainSkillAdapter 应正确调用带 invoke 方法的对象。"""
    index = _make_index(tmp_path)
    match = MatchResult(index.get("document-generator"), 1.0, True, "direct")

    result = SkillExecutor(index, LangChainSkillAdapter(_RealInvokeRunner())).execute(
        match,
        user_query="生成文档",
        fields={"filename": "r.docx", "title": "test"},
    )
    assert result.metrics.execution_success is True
    assert result.output == "langchain-processed:document-generator"


class _CallableOnlyRunner:
    """无 invoke 方法，但可调用的对象。"""

    def __call__(self, prompt: str) -> str:
        return f"callable:{prompt[:10]}"


def test_langchain_adapter_with_callable_runner(tmp_path: Path) -> None:
    """LangChainSkillAdapter 在无 invoke 方法时退回到 callable。"""
    index = _make_index(tmp_path)
    match = MatchResult(index.get("simple-echo"), 1.0, True, "direct")

    result = SkillExecutor(index, LangChainSkillAdapter(_CallableOnlyRunner())).execute(
        match,
        user_query="hello",
    )
    assert result.metrics.execution_success is True
    assert "callable:" in str(result.output)


class _NoInterfaceRunner:
    """既无 invoke 也无 __call__。"""
    pass


def test_langchain_adapter_raises_on_invalid_runner(tmp_path: Path) -> None:
    """无效 runner 对象应导致执行失败但不崩溃。"""
    index = _make_index(tmp_path)
    match = MatchResult(index.get("simple-echo"), 1.0, True, "direct")

    result = SkillExecutor(index, LangChainSkillAdapter(_NoInterfaceRunner())).execute(
        match,
        user_query="test",
    )
    assert result.metrics.execution_success is False


# ---------------------------------------------------------------------------
# SpringAIHttpAdapter — 错误处理
# ---------------------------------------------------------------------------

def test_springai_adapter_handles_connection_error(tmp_path: Path) -> None:
    """SpringAIHttpAdapter 调用不存在的 URL 应触发异常并记录失败。"""
    index = _make_index(tmp_path)
    match = MatchResult(index.get("simple-echo"), 1.0, True, "direct")

    # 使用一个几乎不可能存在的本地端口
    adapter = SpringAIHttpAdapter("http://127.0.0.1:59999/nonexistent", timeout=1.0)
    result = SkillExecutor(index, adapter).execute(match, user_query="test")

    assert result.metrics.execution_success is False
    assert "error" in str(result.output) or result.metrics.execution_success is False


# ---------------------------------------------------------------------------
# CallableSkillAdapter — 通用链入适配器
# ---------------------------------------------------------------------------

def test_callable_adapter_passes_skill_name_and_context(tmp_path: Path) -> None:
    """CallableSkillAdapter 应传递 skill 和完整上下文到处理函数。"""
    captured: dict = {}

    def handler(prompt, skill, context):
        captured["skill_name"] = skill.name
        captured["has_prompt"] = bool(prompt)
        captured["has_context"] = "user_query" in context
        return f"ok:{skill.name}"

    index = _make_index(tmp_path)
    match = MatchResult(index.get("simple-echo"), 1.0, True, "direct")

    result = SkillExecutor(index, CallableSkillAdapter("capture", handler)).execute(
        match, user_query="hello world",
    )
    assert result.metrics.execution_success is True
    assert captured["skill_name"] == "simple-echo"
    assert captured["has_prompt"] is True
    assert captured["has_context"] is True
