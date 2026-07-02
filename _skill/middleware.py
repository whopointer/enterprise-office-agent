"""Skill 中间件入口。"""

from __future__ import annotations

from typing import Any

from .discovery import FileSkillDiscovery
from .prompt import format_skills_prompt
from .models import SkillSource


class SkillsMiddleware:
    """轻量中间件：加载 skill 元数据并追加到 system prompt。"""

    def __init__(
        self,
        sources: SkillSource | list[SkillSource] | tuple[SkillSource, ...],
        *,
        system_prompt_enabled: bool = True,
    ) -> None:
        self.discovery = FileSkillDiscovery(sources)
        self.system_prompt_enabled = system_prompt_enabled

    def before_agent(self, state: dict[str, Any]) -> None:
        """在 agent 执行前加载 SkillIndex，同一 state 中只加载一次。"""
        if "skill_index" in state:
            return
        index = self.discovery.discover()
        state["skill_index"] = index
        state["skills_metadata"] = index.list_skills()
        state["skills_load_errors"] = list(index.load_errors)

    def modify_system_prompt(self, system_prompt: str, state: dict[str, Any]) -> str:
        """把 skill 清单追加到系统提示。"""
        if not self.system_prompt_enabled:
            return system_prompt

        skills = state.get("skills_metadata", [])
        load_errors = tuple(state.get("skills_load_errors", ()))
        source_locations = [
            (label, str(path.resolve()))
            for label, path in zip(self.discovery.source_labels, self.discovery.source_paths, strict=True)
        ]
        skills_prompt = format_skills_prompt(
            skills,
            source_locations=source_locations,
            load_errors=load_errors,
        )
        if not skills_prompt:
            return system_prompt
        return f"{system_prompt.rstrip()}\n\n{skills_prompt}"
