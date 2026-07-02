"""Discovery 阶段测试：SKILL.md 解析、SkillIndex 构建。"""

from __future__ import annotations

from pathlib import Path

from _skill import FileSkillDiscovery
from tests.skill_fixtures import build_pipeline_test_skills, write_skill


def test_discovery_parses_name_description_and_allowed_tools(tmp_path: Path) -> None:
    """Discovery 应解析 name / description / allowed-tools / body / license。"""
    skills_dir = build_pipeline_test_skills(tmp_path)
    index = FileSkillDiscovery(skills_dir).discover()

    expected = {"document-generator", "code-reviewer", "simple-echo", "data-analyzer"}
    assert set(index.skills) == expected
    assert index.load_errors == ()

    doc = index.get("document-generator")
    assert doc is not None
    assert doc.name == "document-generator"
    assert doc.description.startswith("生成 Word 文档报告")
    assert doc.allowed_tools == ("Read", "Bash", "Write")
    assert doc.body.startswith("# Document Generator")

    code = index.get("code-reviewer")
    assert code is not None
    assert code.allowed_tools == ()  # 未声明时为空

    data = index.get("data-analyzer")
    assert data is not None
    assert data.license == "MIT"
    assert data.compatibility == "python>=3.10"


def test_discovery_builds_skill_index(tmp_path: Path) -> None:
    """SkillIndex 的方法正常工作。"""
    skills_dir = build_pipeline_test_skills(tmp_path)
    index = FileSkillDiscovery(skills_dir).discover()

    assert len(index.list_skills()) == 4
    assert index.get("nonexistent") is None
    assert index.get("simple-echo").description == "回显用户输入，用于验证基础 skill 路由和执行管线是否正常。触发条件：用户发送 ping、echo、测试连通性等请求。"


def test_discovery_handles_empty_directory(tmp_path: Path) -> None:
    """空目录不报错，返回无 skill 的 SkillIndex。"""
    empty_dir = tmp_path / "empty_skills"
    empty_dir.mkdir()
    index = FileSkillDiscovery(empty_dir).discover()
    assert index.skills == {}
    assert index.list_skills() == []


def test_discovery_skips_non_skill_directories(tmp_path: Path) -> None:
    """目录下没有 SKILL.md 的子目录应被略过。"""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "not-a-skill").mkdir()
    (skills_dir / "readme.txt").write_text("hello")
    index = FileSkillDiscovery(skills_dir).discover()
    assert index.skills == {}


def test_discovery_handles_unparseable_skill_without_crashing(tmp_path: Path) -> None:
    """非法 SKILL.md 不崩溃，正常 skill 仍加载。"""
    skills_dir = build_pipeline_test_skills(tmp_path)
    bad_dir = skills_dir / "bad-skill"
    bad_dir.mkdir()
    (bad_dir / "SKILL.md").write_text("this has no frontmatter")
    index = FileSkillDiscovery(skills_dir).discover()
    assert "simple-echo" in index.skills
    assert "code-reviewer" in index.skills
    assert len(index.load_errors) >= 1


def test_discovery_source_does_not_exist(tmp_path: Path) -> None:
    """来源目录不存在时，load_errors 记录。"""
    index = FileSkillDiscovery(tmp_path / "not_there").discover()
    assert len(index.load_errors) >= 1


def test_skill_name_validation_rejects_invalid_names(tmp_path: Path) -> None:
    """非法 name 应导致解析失败。"""
    cases = [
        "", "-bad-start", "bad-end-", "Bad-Name", "A" * 65,
    ]
    for bad_name in cases:
        skills_dir = tmp_path / (bad_name or "empty")
        skills_dir.mkdir(parents=True, exist_ok=True)
        skill_dir = skills_dir / "test-skill"
        skill_dir.mkdir(exist_ok=True)
        fm = f"name: {bad_name}\ndescription: test\n"
        (skill_dir / "SKILL.md").write_text(f"---\n{fm}---\n# Body\n")
        index = FileSkillDiscovery(skills_dir).discover()
        assert "test-skill" not in index.skills, f"name='{bad_name}' 应被拒绝"


def test_multi_source_skill_override(tmp_path: Path) -> None:
    """多个 source 同名 skill，后 source 覆盖前 source。"""
    src_a, src_b = tmp_path / "a", tmp_path / "b"
    src_a.mkdir(); src_b.mkdir()
    write_skill(src_a, "overlap", "name: overlap\ndescription: 版本 A\n", "# A")
    write_skill(src_b, "overlap", "name: overlap\ndescription: 版本 B\n", "# B")
    write_skill(src_a, "uniq", "name: uniq\ndescription: 唯一\n", "# uniq")
    index = FileSkillDiscovery([src_a, src_b]).discover()
    assert "uniq" in index.skills
    assert index.get("overlap").description == "版本 B"
