"""真实 skills/ 库存质量测试。"""

from __future__ import annotations

from pathlib import Path

from _skill import FileSkillDiscovery


def test_real_skills_inventory_loads_without_errors() -> None:
    """真实 skills 目录应全部可被 Discovery 加载。"""
    repo_root = Path(__file__).resolve().parents[1]
    skills_dir = repo_root / "skills"

    index = FileSkillDiscovery(skills_dir).discover()

    assert len(index.skills) == 21
    assert index.load_errors == ()
    assert all(skill.name for skill in index.list_skills())
    assert all(skill.description for skill in index.list_skills())


def test_real_skills_resource_directories_are_measurable() -> None:
    """统计真实 skill 的 references/assets/scripts 目录，确保库存指标可采集。"""
    repo_root = Path(__file__).resolve().parents[1]
    skills_dir = repo_root / "skills"
    index = FileSkillDiscovery(skills_dir).discover()

    resource_counts = {
        "references": 0,
        "assets": 0,
        "scripts": 0,
    }

    for skill in index.list_skills():
        skill_dir = Path(skill.directory)
        for resource_name in resource_counts:
            resource_dir = skill_dir / resource_name
            if resource_dir.is_dir() and any(resource_dir.iterdir()):
                resource_counts[resource_name] += 1

    assert sum(resource_counts.values()) > 0
    assert resource_counts["references"] > 0


def test_real_skill_descriptions_stay_within_parser_limit() -> None:
    """description 已被解析器截断到限制内，避免路由 prompt 非预期膨胀。"""
    repo_root = Path(__file__).resolve().parents[1]
    index = FileSkillDiscovery(repo_root / "skills").discover()

    lengths = [len(skill.description) for skill in index.list_skills()]

    assert lengths
    assert max(lengths) <= 1024
    assert sum(lengths) / len(lengths) > 20
