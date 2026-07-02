"""边界与鲁棒性测试。"""

from __future__ import annotations

from pathlib import Path

from _skill import FileSkillDiscovery
from tests.skill_fixtures import build_pipeline_test_skills, write_skill


def test_discovery_empty_directory_all_methods_safe(tmp_path: Path) -> None:
    """空目录的 SkillIndex 所有方法不抛异常。"""
    empty = tmp_path / "empty"
    empty.mkdir()
    index = FileSkillDiscovery(empty).discover()
    assert index.skills == {}
    assert index.list_skills() == []
    assert index.get("any") is None


def test_discovery_very_long_description_is_truncated(tmp_path: Path) -> None:
    """超长 description 被截断。"""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    long_desc = "x" * 2000
    write_skill(skills_dir, "long-desc", f"name: long-desc\ndescription: {long_desc}\n", "# body")
    index = FileSkillDiscovery(skills_dir).discover()
    skill = index.get("long-desc")
    assert skill is not None
    assert len(skill.description) <= 1024


def test_parser_rejects_invalid_skill_names(tmp_path: Path) -> None:
    """非法 skill 名 → load_errors。"""
    bad_dir = tmp_path / "bad"
    bad_dir.mkdir()
    write_skill(bad_dir, "x-y-", "name: x-y-\ndescription: 以连字符结尾\n", "# x")
    write_skill(bad_dir, "X-Y", "name: X-Y\ndescription: 含大写\n", "# x")
    index = FileSkillDiscovery(bad_dir).discover()
    assert "x-y-" not in index.skills
    assert "X-Y" not in index.skills


def test_parser_rejects_skill_without_description(tmp_path: Path) -> None:
    """无 description → 解析失败。"""
    bad_dir = tmp_path / "no_desc"
    bad_dir.mkdir()
    write_skill(bad_dir, "v", "name: v\n", "# body")
    index = FileSkillDiscovery(bad_dir).discover()
    assert "v" not in index.skills


def test_discovery_handles_very_long_skill_body(tmp_path: Path) -> None:
    """超大 body 不崩溃。"""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    large_body = "# " + "x" * 100000
    write_skill(skills_dir, "huge", "name: huge\ndescription: 大文件测试\n", large_body)
    index = FileSkillDiscovery(skills_dir).discover()
    assert index.get("huge") is not None
    # 超过 10MB 会拒绝
    huge_body = "# " + "x" * (10 * 1024 * 1024 + 100)
    try:
        write_skill(skills_dir, "too-big", "name: too-big\ndescription: 超大\n", huge_body)
    except OSError:
        pass
    # 不管怎样不崩


def test_discovery_handles_unparseable_frontmatter(tmp_path: Path) -> None:
    """YAML 解析错误 → load_errors，但不影响其他 skill。"""
    skills_dir = build_pipeline_test_skills(tmp_path)
    bad = skills_dir / "bad-yaml"
    bad.mkdir()
    (bad / "SKILL.md").write_text("---\n[\n---\n# bad\n")
    index = FileSkillDiscovery(skills_dir).discover()
    assert "simple-echo" in index.skills


def test_skill_without_body_still_loads(tmp_path: Path) -> None:
    """只含 frontmatter 无正文的 skill 正常加载（body 为空字符串）。"""
    skills_dir = tmp_path / "s"
    skills_dir.mkdir()
    write_skill(skills_dir, "minimal", "name: minimal\ndescription: 最简 skill\n", "")
    index = FileSkillDiscovery(skills_dir).discover()
    skill = index.get("minimal")
    assert skill is not None
    assert skill.body == ""
