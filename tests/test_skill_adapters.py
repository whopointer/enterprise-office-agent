"""所有适配器的真实执行链路测试。"""

from __future__ import annotations

from pathlib import Path
import os

import pytest

from core.executor import SkillExecutor
from _skill import (
    CallableSkillAdapter,
    FileSkillDiscovery,
)
from adapters.skill_adapters import (
    LangChainSkillAdapter,
    OpenAICompatibleSkillAdapter,
    SpringAIHttpAdapter,
)
from llm.skill_router import load_skill_env
from tests.conftest import get_runtime_collector
from tests.fakes import TestWordDocumentAdapter
from tests.skill_fixtures import build_pipeline_test_skills

load_skill_env()


def _record(skill_name, metrics):
    get_runtime_collector().record(skill_name, metrics)


def _make_skill(tmp_path: Path):
    index = FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()
    return index.get("simple-echo")


# ---------------------------------------------------------------------------
# TestWordDocumentAdapter — 测试专用 docx 生成
# ---------------------------------------------------------------------------

def test_word_document_adapter_generates_docx_artifact(tmp_path: Path) -> None:
    """TestWordDocument fake 应在指定路径生成 .docx 文件。"""
    output_path = tmp_path / "custom-report.docx"
    skill = _make_skill(tmp_path)
    result = SkillExecutor(
        FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover(),
        TestWordDocumentAdapter(),
    ).execute(
        skill,
        user_query="生成报告",
        fields={"output_path": str(output_path), "title": "测试报告", "content": "内容"},
    )
    _record(skill.name, result.metrics)
    assert result.metrics.execution_success is True
    assert output_path.exists()


def test_word_document_adapter_uses_default_filename(tmp_path: Path) -> None:
    """不指定 output_path 时使用 skill-output.docx 作为默认文件名。"""
    skill = _make_skill(tmp_path)
    result = SkillExecutor(
        FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover(),
        TestWordDocumentAdapter(),
    ).execute(
        skill,
        user_query="生成报告",
        fields={"title": "默认文件名测试"},
    )
    _record(skill.name, result.metrics)
    assert result.metrics.execution_success is True
    default_path = Path("skill-output.docx")
    assert default_path.exists()
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
    skill = _make_skill(tmp_path)
    result = SkillExecutor(
        FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover(),
        OpenAICompatibleSkillAdapter(),
    ).execute(skill, user_query="回复: 你好")
    _record(skill.name, result.metrics)
    assert result.metrics.execution_success is True
    assert len(str(result.output)) > 0


# ---------------------------------------------------------------------------
# LangChainSkillAdapter
# ---------------------------------------------------------------------------

class _Runner:
    def invoke(self, payload: dict) -> str:
        return f"lc:{payload.get('skill', '?')}"


def test_langchain_adapter_with_runner(tmp_path: Path) -> None:
    """LangChainSkillAdapter 应调用 invoke 方法。"""
    skill = _make_skill(tmp_path)
    result = SkillExecutor(
        FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover(),
        LangChainSkillAdapter(_Runner()),
    ).execute(skill, user_query="test")
    _record(skill.name, result.metrics)
    assert result.metrics.execution_success is True
    assert result.output == "lc:simple-echo"


class _CallableOnly:
    def __call__(self, prompt: str) -> str:
        return f"callable:{prompt[:10]}"


def test_langchain_adapter_with_callable(tmp_path: Path) -> None:
    """无 invoke 方法时退到 callable。"""
    skill = _make_skill(tmp_path)
    result = SkillExecutor(
        FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover(),
        LangChainSkillAdapter(_CallableOnly()),
    ).execute(skill, user_query="hello")
    _record(skill.name, result.metrics)
    assert result.metrics.execution_success is True
    assert "callable:" in str(result.output)


def test_langchain_adapter_raises_on_invalid_runner(tmp_path: Path) -> None:
    """无效 runner → execution_success=False。"""
    skill = _make_skill(tmp_path)
    result = SkillExecutor(
        FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover(),
        LangChainSkillAdapter(object()),
    ).execute(skill, user_query="test")
    _record(skill.name, result.metrics)
    assert result.metrics.execution_success is False


# ---------------------------------------------------------------------------
# SpringAIHttpAdapter
# ---------------------------------------------------------------------------

def test_springai_adapter_handles_connection_error(tmp_path: Path) -> None:
    """无效 URL → 执行失败不崩溃。"""
    skill = _make_skill(tmp_path)
    result = SkillExecutor(
        FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover(),
        SpringAIHttpAdapter("http://127.0.0.1:59999/x", timeout=1.0),
    ).execute(skill, user_query="test")
    _record(skill.name, result.metrics)
    assert result.metrics.execution_success is False


# ---------------------------------------------------------------------------
# CallableSkillAdapter
# ---------------------------------------------------------------------------

def test_callable_adapter_passes_context(tmp_path: Path) -> None:
    """CallableSkillAdapter 传递 skill 名和 user_query 到 handler。"""
    captured: dict = {}

    def handler(prompt, skill, context):
        captured["name"] = skill.name
        captured["query"] = context.get("user_query", "")
        return "ok"

    skill = _make_skill(tmp_path)
    result = SkillExecutor(
        FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover(),
        CallableSkillAdapter("cap", handler),
    ).execute(skill, user_query="hello world")
    _record(skill.name, result.metrics)
    assert result.metrics.execution_success is True
    assert captured["name"] == "simple-echo"
    assert captured["query"] == "hello world"
