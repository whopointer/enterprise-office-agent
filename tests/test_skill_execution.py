"""Execution 阶段测试：prompt 构建、适配器调用、token 估算。"""

from __future__ import annotations

from pathlib import Path

from core.executor import SkillExecutor, TokenTracker
from _skill import (
    CallableSkillAdapter,
    FileSkillDiscovery,
)
from tests.conftest import get_runtime_collector
from tests.skill_fixtures import build_pipeline_test_skills


def _record(skill_name, metrics):
    get_runtime_collector().record(skill_name, metrics)


def test_execution_builds_prompt_with_skill_body(tmp_path: Path) -> None:
    index = FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()
    skill = index.get("simple-echo")
    adapter = CallableSkillAdapter("test", lambda p, s, c: "ok")
    result = SkillExecutor(index, adapter).execute(skill, user_query="hello world")
    _record(skill.name, result.metrics)
    assert result.metrics.execution_success is True
    assert "Skill: simple-echo" in result.context.prompt


def test_execution_passes_fields_to_prompt(tmp_path: Path) -> None:
    index = FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()
    adapter = CallableSkillAdapter("test", lambda p, s, c: "ok")
    skill = index.get("document-generator")
    result = SkillExecutor(index, adapter).execute(
        skill, user_query="生成报告", fields={"filename": "r.docx", "title": "周报"},
    )
    _record(skill.name, result.metrics)
    assert "filename" in result.context.prompt


def test_execution_records_token_metrics(tmp_path: Path) -> None:
    index = FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()
    adapter = CallableSkillAdapter("test", lambda p, s, c: "pong")
    skill = index.get("simple-echo")
    result = SkillExecutor(index, adapter).execute(skill, user_query="ping")
    _record(skill.name, result.metrics)
    assert result.metrics.token_metrics.total_tokens > 0


def test_execution_records_latency(tmp_path: Path) -> None:
    index = FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()
    adapter = CallableSkillAdapter("test", lambda p, s, c: "ok")
    skill = index.get("simple-echo")
    result = SkillExecutor(index, adapter).execute(skill, user_query="test")
    _record(skill.name, result.metrics)
    assert result.metrics.latency_ms > 0


def test_execution_adapter_error_is_captured(tmp_path: Path) -> None:
    index = FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()

    def crash(_p, _s, _c):
        raise RuntimeError("boom")

    skill = index.get("simple-echo")
    result = SkillExecutor(index, CallableSkillAdapter("bad", crash)).execute(skill, user_query="test")
    _record(skill.name, result.metrics)
    assert result.metrics.execution_success is False


def test_token_tracker_overhead_calculation(tmp_path: Path) -> None:
    index = FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()
    skill = index.get("simple-echo")
    adapter = CallableSkillAdapter("test", lambda p, s, c: "small")

    baseline = SkillExecutor(index, adapter, token_tracker=TokenTracker()).execute(skill, user_query="ping")
    _record(skill.name, baseline.metrics)

    tracker = TokenTracker(baseline_tokens=baseline.metrics.token_metrics.total_tokens)
    result = SkillExecutor(index, adapter, token_tracker=tracker).execute(skill, user_query="ping with more text")
    _record(skill.name, result.metrics)

    assert result.metrics.token_metrics.overhead_pct is not None
    assert result.metrics.token_metrics.overhead_pct > 0
