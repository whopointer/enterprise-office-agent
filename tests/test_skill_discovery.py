"""Discovery 阶段测试：文件系统扫描、SKILL.md 解析、SkillIndex 构建。"""

from __future__ import annotations

from pathlib import Path

import pytest

from _skill import (
    FileSkillDiscovery,
    SkillDefinition,
)
from tests.skill_fixtures import build_pipeline_test_skills, write_skill


def test_discovery_parses_skills_with_full_dsl(tmp_path: Path) -> None:
    """Discovery 应正确解析 name / description / triggers / red_lines / references / assets / token_estimate。"""
    skills_dir = build_pipeline_test_skills(tmp_path)
    index = FileSkillDiscovery(skills_dir).discover()

    expected = {"document-generator", "skill-index", "security-auditor", "simple-echo", "pattern-matcher"}
    assert set(index.skills) == expected
    assert index.load_errors == ()

    doc = index.get("document-generator")
    assert doc is not None
    assert doc.description.startswith("生成 Word")
    assert doc.triggers["keywords"] == ["word", "docx", "document", "文档", "报告", "生成报告"]
    assert doc.triggers["patterns"] == ["生成.*(?:报告|文档|docx|word)"]
    assert [r.field for r in doc.red_lines] == ["filename", "title"]
    assert doc.assets[0].path == "assets/report-template.docx"
    assert doc.assets[0].exists is True
    assert doc.assets[0].type == "word_document"
    assert doc.token_estimate.system_prompt == 120
    assert doc.token_estimate.per_asset == 40

    # skill-index 引用了 document-generator
    assert index.ref_graph["skill-index"] == ("document-generator",)

    # simple-echo 是最简 skill
    echo = index.get("simple-echo")
    assert echo is not None
    assert echo.red_lines == ()
    assert echo.references == ()
    assert echo.assets == ()


def test_discovery_builds_ref_graph_and_asset_map(tmp_path: Path) -> None:
    """Discovery 产出的 index.ref_graph 和 index.asset_map 结构正确。"""
    skills_dir = build_pipeline_test_skills(tmp_path)
    index = FileSkillDiscovery(skills_dir).discover()

    assert index.ref_graph["skill-index"] == ("document-generator",)
    assert index.ref_graph["document-generator"] == ()
    assert index.redline_rules["security-auditor"] is not None
    assert len(index.redline_rules["security-auditor"]) == 3

    doc_assets = index.asset_map["document-generator"]
    assert len(doc_assets) == 1
    assert doc_assets[0].exists is True


def test_discovery_handles_empty_directory(tmp_path: Path) -> None:
    """空目录不报错，返回无 skill 的 SkillIndex。"""
    empty_dir = tmp_path / "empty_skills"
    empty_dir.mkdir()
    index = FileSkillDiscovery(empty_dir).discover()

    assert index.skills == {}
    assert index.list_skills() == []
    assert index.ref_graph == {}


def test_discovery_skips_non_skill_directories(tmp_path: Path) -> None:
    """目录下没有 SKILL.md 的子目录应被略过。"""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "not-a-skill").mkdir()
    (skills_dir / "readme.txt").write_text("hello")

    index = FileSkillDiscovery(skills_dir).discover()
    assert index.skills == {}


def test_discovery_handles_unparseable_skill_without_crashing(tmp_path: Path) -> None:
    """一个非法 SKILL.md 不应导致整个 discovery 失败，其他正常 skill 仍可用。"""
    skills_dir = build_pipeline_test_skills(tmp_path)

    bad_dir = skills_dir / "bad-skill"
    bad_dir.mkdir()
    (bad_dir / "SKILL.md").write_text("this has no frontmatter at all")

    index = FileSkillDiscovery(skills_dir).discover()
    assert "document-generator" in index.skills
    assert "simple-echo" in index.skills
    assert len(index.load_errors) >= 1
    assert any("bad-skill" in err for err in index.load_errors)


def test_discovery_source_does_not_exist(tmp_path: Path) -> None:
    """来源目录不存在时，load_errors 应记录。"""
    nonexistent = tmp_path / "does_not_exist"
    index = FileSkillDiscovery(nonexistent).discover()

    assert len(index.load_errors) >= 1
    assert "不存在" in index.load_errors[0]


def test_skill_name_validation_rejects_invalid_names(tmp_path: Path) -> None:
    """SKILL.md 中 name 不符合规范应导致解析失败。"""
    cases = [
        ("", "缺少 name"),
        ("-bad", "不能以连字符开头"),
        ("bad-", "不能以连字符结尾"),
        ("bad--name", "不能包含连续连字符"),
        ("A" * 65, "超过 64 字符"),
        ("Bad-Name", "只能包含小写字母数字和连字符"),
    ]
    for bad_name, _reason in cases:
        skills_dir = tmp_path / bad_name.replace("-", "_") if bad_name else tmp_path / "empty_name"
        skills_dir.mkdir(parents=True, exist_ok=True)
        skill_dir = skills_dir / "test-skill"
        skill_dir.mkdir(exist_ok=True)
        fm = f"name: {bad_name}\ndescription: test\n"
        (skill_dir / "SKILL.md").write_text(f"---\n{fm}---\n# Body\n")

        index = FileSkillDiscovery(skills_dir).discover()
        assert "test-skill" not in index.skills, f"name='{bad_name}' 应被拒绝但未被拒绝"


def test_multi_source_skill_override(tmp_path: Path) -> None:
    """多个 source 中同名 skill，后 source 覆盖前 source。"""
    src_a = tmp_path / "src_a"
    src_b = tmp_path / "src_b"
    src_a.mkdir()
    src_b.mkdir()

    write_skill(src_a, "overlap", "name: overlap\ndescription: 版本 A\n", "# A")
    write_skill(src_b, "overlap", "name: overlap\ndescription: 版本 B - 覆盖版本\n", "# B")
    write_skill(src_a, "only-in-a", "name: only-in-a\ndescription: 仅在 A\n", "# only A")

    index = FileSkillDiscovery([src_a, src_b]).discover()
    assert "only-in-a" in index.skills
    assert "overlap" in index.skills
    assert index.get("overlap").description == "版本 B - 覆盖版本"
