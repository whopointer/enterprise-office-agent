"""Execution 阶段测试：上下文装载、适配器调用、执行指标。"""

from __future__ import annotations

from pathlib import Path

from _skill import (
    CallableSkillAdapter,
    FileSkillDiscovery,
    MatchResult,
    MetricsCollector,
    SkillActivator,
    SkillExecutor,
    TokenTracker,
)
from tests.skill_fixtures import build_pipeline_test_skills


def test_execution_expands_references(tmp_path: Path) -> None:
    """技能间引用应被正确展开并注入上下文。"""
    index = FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()
    match = SkillActivator(index).activate("列出所有已注册的 skill")
    assert isinstance(match, MatchResult)
    assert match.skill.name == "skill-index"

    adapter = CallableSkillAdapter("test-adapter", lambda p, s, c: f"done:{s.name}")
    result = SkillExecutor(index, adapter).execute(match, user_query="列出所有 skill")

    assert result.output == "done:skill-index"
    assert "document-generator" in result.context.reference_bodies
    assert result.metrics.reference_load_rate == 1.0
    assert result.metrics.context_integrity_pass is True


def test_execution_injects_assets(tmp_path: Path) -> None:
    """Asset 文件应在上下文中注入，并在指标中反映。"""
    index = FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()
    match = SkillActivator(index).activate("生成 word 报告",
                                            fields={"filename": "r.docx", "title": "Q1"})
    assert isinstance(match, MatchResult)
    assert match.skill.name == "document-generator"

    adapter = CallableSkillAdapter("test-adapter", lambda p, s, c: "ok")
    result = SkillExecutor(index, adapter).execute(match, user_query="生成报告")

    assert result.metrics.asset_load_rate == 1.0
    assert result.asset_paths
    # asset_paths 包含 resolved_path（绝对路径），检查是否包含文件名
    assert any("report-template.docx" in p for p in result.asset_paths)
    assert result.metrics.context_integrity_pass is True


def test_execution_records_token_metrics(tmp_path: Path) -> None:
    """执行后应产出 token 估算指标。"""
    index = FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()
    match = SkillActivator(index).activate("echo ping test")
    assert isinstance(match, MatchResult)

    adapter = CallableSkillAdapter("test-adapter", lambda p, s, c: "pong")
    result = SkillExecutor(index, adapter).execute(match, user_query="ping")

    assert result.metrics.token_metrics.total_tokens > 0
    assert result.metrics.token_metrics.input_tokens > 0
    assert result.metrics.execution_success is True
    assert result.metrics.adapter_name == "test-adapter"


def test_execution_records_latency(tmp_path: Path) -> None:
    """延迟指标应大于 0。"""
    index = FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()
    match = SkillActivator(index).activate("echo test")
    assert isinstance(match, MatchResult)

    adapter = CallableSkillAdapter("test", lambda p, s, c: "ok")
    result = SkillExecutor(index, adapter).execute(match, user_query="test")

    assert result.metrics.latency_ms > 0


def test_execution_with_missing_references_does_not_crash(tmp_path: Path) -> None:
    """引用的 skill 不存在时应标记 missing 但不崩溃。"""
    index = FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()

    # skill-index 引用了 document-generator，需要确认 document-generator 存在
    match = SkillActivator(index).activate("搜索 skill 列表")
    assert isinstance(match, MatchResult)
    assert match.skill.name == "skill-index"

    adapter = CallableSkillAdapter("test", lambda p, s, c: "ok")

    # 直接构造一个 MatchResult，但指向一个不存在的 index
    from _skill.models import SkillDefinition, TokenEstimate, SkillMetricsSpec
    fake_skill = SkillDefinition(
        name="missing-ref-skill", description="test", path="/fake", directory="/fake",
        body="test", references=("nonexistent",), token_estimate=TokenEstimate(),
        metrics=SkillMetricsSpec(),
    )
    result = SkillExecutor(index, adapter).execute(
        MatchResult(fake_skill, 1.0, True, "test"),
        user_query="test",
    )
    assert result.metrics.reference_load_rate == 0.0
    assert result.metrics.missing_reference_count == 1
    assert result.metrics.context_integrity_pass is False


def test_execution_adapter_error_is_captured(tmp_path: Path) -> None:
    """适配器抛异常时执行不崩溃，指标标记失败。"""
    index = FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()
    match = SkillActivator(index).activate("echo test")
    assert isinstance(match, MatchResult)

    def failing(_prompt, _skill, _context):
        raise RuntimeError("模拟适配器崩溃")

    adapter = CallableSkillAdapter("failing-adapter", failing)
    result = SkillExecutor(index, adapter).execute(match, user_query="test")

    assert result.metrics.execution_success is False
    assert "error" in str(result.output)
