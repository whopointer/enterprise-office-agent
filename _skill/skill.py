"""Skill 中间件门面导出。"""

from __future__ import annotations

from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from _skill.discovery import FileSkillDiscovery
    from _skill.middleware import SkillsMiddleware
    from _skill.parser import parse_skill_file
    from _skill.prompt import format_skills_prompt
    from _skill.models import (
        CallableSkillAdapter,
        SkillAdapter,
        SkillDefinition,
        SkillIndex,
        TokenMetrics,
    )
else:
    from .discovery import FileSkillDiscovery
    from .middleware import SkillsMiddleware
    from .parser import parse_skill_file
    from .prompt import format_skills_prompt
    from .models import (
        CallableSkillAdapter,
        SkillAdapter,
        SkillDefinition,
        SkillIndex,
        TokenMetrics,
    )

__all__ = [
    "CallableSkillAdapter",
    "FileSkillDiscovery",
    "SkillAdapter",
    "SkillDefinition",
    "SkillIndex",
    "SkillsMiddleware",
    "TokenMetrics",
    "format_skills_prompt",
    "parse_skill_file",
]


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parents[1]
    skills_dir = repo_root / "skills"
    index = FileSkillDiscovery(skills_dir).discover()
    print(
        format_skills_prompt(
            index.list_skills(),
            source_locations=[("skills", str(skills_dir))],
            load_errors=index.load_errors,
        )
    )
