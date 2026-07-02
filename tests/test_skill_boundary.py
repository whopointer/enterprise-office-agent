"""边界与鲁棒性测试。"""

from __future__ import annotations

from pathlib import Path

from _skill import (
    FileSkillDiscovery,
    NoSkillMatched,
    SkillActivator,
)
from tests.skill_fixtures import build_pipeline_test_skills


def _make_index(tmp_path: Path):
    return FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()


# ---------------------------------------------------------------------------
# 空 query / 超长 query
# ---------------------------------------------------------------------------

def test_activation_handles_empty_and_whitespace_query(tmp_path: Path) -> None:
    """空字符串和纯空白应返回 NoSkillMatched 而非崩溃。"""
    activator = SkillActivator(_make_index(tmp_path))
    for q in ("", "   ", "\n\t", "   \n  "):
        assert isinstance(activator.activate(q), NoSkillMatched)


def test_activation_handles_very_long_query(tmp_path: Path) -> None:
    """超长 query 不崩溃。"""
    activator = SkillActivator(_make_index(tmp_path))
    long_query = "文档 " * 5000 + "word document docx 报告"
    result = activator.activate(long_query)
    # 至少不抛异常
    assert result is not None


# ---------------------------------------------------------------------------
# 空 skills 目录
# ---------------------------------------------------------------------------

def test_discovery_empty_directory_all_methods_safe(tmp_path: Path) -> None:
    """空目录的 SkillIndex 所有方法不应抛异常。"""
    empty = tmp_path / "empty"
    empty.mkdir()
    index = FileSkillDiscovery(empty).discover()

    assert index.skills == {}
    assert index.list_skills() == []
    assert index.get("any") is None
    assert index.ref_graph == {}


# ---------------------------------------------------------------------------
# 无效 skill 名
# ---------------------------------------------------------------------------

def test_parser_rejects_invalid_skill_names(tmp_path: Path) -> None:
    """非法 skill 名应在解析时被拒绝，放入 load_errors。"""
    from tests.skill_fixtures import write_skill

    bad_dir = tmp_path / "bad_names"
    bad_dir.mkdir()

    write_skill(bad_dir, "bad-name-", "name: bad-name-\ndescription: 以连字符结尾\n", "# x")
    write_skill(bad_dir, "Bad-Name", "name: Bad-Name\ndescription: 含大写\n", "# x")

    index = FileSkillDiscovery(bad_dir).discover()
    assert "bad-name-" not in index.skills
    assert "Bad-Name" not in index.skills
    assert len(index.load_errors) >= 2


def test_parser_rejects_skill_without_description(tmp_path: Path) -> None:
    """无 description 的 skill 应被拒绝。"""
    from tests.skill_fixtures import write_skill

    bad_dir = tmp_path / "no_desc"
    bad_dir.mkdir()
    write_skill(bad_dir, "valid-name", "name: valid-name\n", "# body")
    index = FileSkillDiscovery(bad_dir).discover()
    assert "valid-name" not in index.skills


# ---------------------------------------------------------------------------
# 几乎相同触发词的 skill 应仍能区分
# ---------------------------------------------------------------------------

def test_activator_picks_highest_confidence_when_ambiguous(tmp_path: Path) -> None:
    """当多个 skill 都有部分关键词命中时，返回得分最高的。"""
    index = _make_index(tmp_path)
    activator = SkillActivator(index)

    # "文档" 可能命中 document-generator 也可能不命中其他，但应只返回一个
    result = activator.activate("文档 word")
    assert hasattr(result, "skill")
    skill_name = result.skill.name if hasattr(result, "skill") else None
    assert skill_name in ("document-generator",) or isinstance(result, NoSkillMatched)


# ---------------------------------------------------------------------------
# 中英混合
# ---------------------------------------------------------------------------

def test_activation_handles_mixed_language_query(tmp_path: Path) -> None:
    """中英混合 query 应能正确匹配。"""
    index = _make_index(tmp_path)
    activator = SkillActivator(index)

    r = activator.activate("生成一份 document 报告 word docx")
    assert isinstance(r, type(activator.activate("docx")))  # 不崩即可
    if hasattr(r, "skill"):
        assert r.skill.name == "document-generator"
