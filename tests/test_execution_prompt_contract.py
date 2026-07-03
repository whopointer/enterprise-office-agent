"""执行 prompt 组装契约测试。"""

from __future__ import annotations

from pathlib import Path

from _skill import CallableSkillAdapter, FileSkillDiscovery
from core.executor import SkillExecutor
from tests.skill_fixtures import build_pipeline_test_skills


def test_execution_prompt_contains_required_sections(tmp_path: Path) -> None:
    """执行 prompt 必须包含 skill、用户请求、字段和完整 body。"""
    index = FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()
    skill = index.get("document-generator")
    captured: dict[str, str] = {}

    def handler(prompt, _skill, _context):
        captured["prompt"] = prompt
        return "ok"

    result = SkillExecutor(index, CallableSkillAdapter("capture", handler)).execute(
        skill,
        user_query="生成周报",
        fields={"filename": "weekly.docx", "template_name": "standard"},
    )

    prompt = captured["prompt"]
    assert result.metrics.execution_success is True
    assert "# Skill: document-generator" in prompt
    assert "## Skill 描述" in prompt
    assert "## 用户请求" in prompt
    assert "生成周报" in prompt
    assert "## 结构化字段" in prompt
    assert '"filename": "weekly.docx"' in prompt
    assert '"template_name": "standard"' in prompt
    assert "## Skill 指令" in prompt
    assert "# Document Generator" in prompt


def test_execution_context_matches_adapter_input(tmp_path: Path) -> None:
    """ExecutionResult.context.prompt 应与 adapter 收到的 prompt 一致。"""
    index = FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()
    skill = index.get("simple-echo")
    captured: dict[str, str] = {}

    def handler(prompt, _skill, _context):
        captured["prompt"] = prompt
        return "ok"

    result = SkillExecutor(index, CallableSkillAdapter("capture", handler)).execute(skill, user_query="ping")

    assert result.context.prompt == captured["prompt"]
    assert result.metrics.token_metrics.input_tokens > 0
