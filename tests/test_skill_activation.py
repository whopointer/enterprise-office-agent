"""Activation 阶段测试：关键词匹配、正则匹配、红线校验。"""

from __future__ import annotations

from pathlib import Path

from _skill import (
    FileSkillDiscovery,
    MatchResult,
    NoSkillMatched,
    RedLineViolation,
    SkillActivator,
)
from tests.skill_fixtures import build_pipeline_test_skills


def test_activator_matches_by_keyword(tmp_path: Path) -> None:
    """关键词匹配：中文和英文关键词都应命中。"""
    index = FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()
    activator = SkillActivator(index)

    # 中文关键词（document-generator 有红线字段，不传则被拦，但确认匹配到了）
    r = activator.activate("帮我生成一份 word 文档报告")
    assert hasattr(r, "skill")
    assert r.skill.name == "document-generator"

    # 英文关键词
    r = activator.activate("echo this message back to me")
    assert isinstance(r, MatchResult)
    assert r.skill.name == "simple-echo"

    # 组合关键词（security-auditor 有红线字段，不传被拦但确认匹配到了）
    r = activator.activate("对项目做一次安全检查审计")
    assert hasattr(r, "skill")
    assert r.skill.name == "security-auditor"


def test_activator_matches_by_pattern(tmp_path: Path) -> None:
    """正则 pattern 匹配应能触发纯 pattern 驱动的 skill。"""
    index = FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()
    activator = SkillActivator(index)

    # keyword 为空、纯靠 pattern 的 skill 应按正则命中
    r = activator.activate("请创建一个表格展示数据")
    assert r.skill.name == "pattern-matcher"

    # 不同 query 命中不同 pattern
    r = activator.activate("绘制一张图表供汇报用")
    assert r.skill.name == "pattern-matcher"

    r = activator.activate("生成一份表格填入数据")
    assert r.skill.name == "pattern-matcher"


def test_activator_returns_no_skill_matched_for_irrelevant_query(tmp_path: Path) -> None:
    """无关请求应返回 NoSkillMatched。"""
    index = FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()
    activator = SkillActivator(index)

    r = activator.activate("今天北京的天气怎么样")
    assert isinstance(r, NoSkillMatched)

    r = activator.activate("帮我点一份外卖")
    assert isinstance(r, NoSkillMatched)


def test_activation_blocks_on_single_missing_redline_field(tmp_path: Path) -> None:
    """缺一个红线字段应返回 RedLineViolation。"""
    index = FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()
    activator = SkillActivator(index)

    # 只给 filename，缺 title
    r = activator.activate("生成 word 文档", fields={"filename": "report.docx"})
    assert isinstance(r, RedLineViolation)
    assert r.skill.name == "document-generator"
    assert r.reason == "缺少报告标题"


def test_activation_blocks_on_multiple_missing_redline_fields(tmp_path: Path) -> None:
    """缺多个红线字段时违反理由应包含所有缺失字段。"""
    index = FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()
    activator = SkillActivator(index)

    # security-auditor 缺 scope, language, output_format
    r = activator.activate("执行代码安全检查")
    assert isinstance(r, RedLineViolation)
    assert r.skill.name == "security-auditor"
    assert "审查范围" in r.reason
    assert "编程语言" in r.reason
    assert "输出格式" in r.reason


def test_activation_passes_when_all_redline_fields_present(tmp_path: Path) -> None:
    """红线字段齐全时应正常返回 MatchResult。"""
    index = FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()
    activator = SkillActivator(index)

    r = activator.activate("生成 word 文档", fields={"filename": "r.docx", "title": "周报"})
    assert isinstance(r, MatchResult)
    assert r.skill.name == "document-generator"
    assert r.redline_pass is True

    r = activator.activate("安全检查", fields={
        "scope": "./src", "language": "python", "output_format": "markdown",
    })
    assert isinstance(r, MatchResult)
    assert r.skill.name == "security-auditor"


def test_activation_blocks_empty_value_as_missing(tmp_path: Path) -> None:
    """空字符串 / 空列表 / 空字典应视作字段缺失。"""
    index = FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()
    activator = SkillActivator(index)

    # 空字符串
    r = activator.activate("生成报告", fields={"filename": "", "title": "hello"})
    assert isinstance(r, RedLineViolation)

    # 空列表
    r = activator.activate("生成报告", fields={"filename": [], "title": "hello"})
    assert isinstance(r, RedLineViolation)

    # 空字典
    r = activator.activate("生成报告", fields={"filename": {}, "title": "hello"})
    assert isinstance(r, RedLineViolation)


def test_activation_confidence_threshold(tmp_path: Path) -> None:
    """低置信度匹配应被 min_confidence 过滤。"""
    index = FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()
    strict_activator = SkillActivator(index, min_confidence=0.6)

    # "报告" 只命中 document-generator 的一个 keyword，score 大约 0.2+0.05+...
    r = strict_activator.activate("报告")
    assert isinstance(r, NoSkillMatched)

    # 降低阈值后应能匹配（但有红线字段，会被拦截）
    loose_activator = SkillActivator(index, min_confidence=0.1)
    r = loose_activator.activate("报告")
    assert r.skill.name == "document-generator"
    # 未传红线字段，应为 RedLineViolation 而非 NoSkillMatched
    from _skill import RedLineViolation
    assert isinstance(r, RedLineViolation)


def test_activation_handles_empty_query(tmp_path: Path) -> None:
    """空 query 或纯标点应返回 NoSkillMatched。"""
    index = FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()
    activator = SkillActivator(index)

    for q in ("", "   ", "。，、！？", "..."):
        r = activator.activate(q)
        assert isinstance(r, NoSkillMatched), f"query='{q}' 应返回 NoSkillMatched"


def test_skill_without_redlines_always_passes_activation(tmp_path: Path) -> None:
    """无红线规则的 skill 在匹配成功后应直接返回 MatchResult。"""
    index = FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()
    activator = SkillActivator(index)

    r = activator.activate("echo test 消息", fields={})
    assert isinstance(r, MatchResult)
    assert r.skill.name == "simple-echo"
    assert r.redline_pass is True
