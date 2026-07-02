"""Discovery 阶段：从文件系统构建 SkillIndex。"""

from __future__ import annotations

from pathlib import Path
import logging

from .parser import parse_skill_file
from .models import SkillDefinition, SkillIndex, SkillSource
from .utils import is_labeled_source, source_label, source_path

logger = logging.getLogger(__name__)


class FileSkillDiscovery:
    """Discovery 阶段：从文件系统扫描 skill 目录并构建 SkillIndex。"""

    def __init__(self, sources: SkillSource | list[SkillSource] | tuple[SkillSource, ...]):
        if isinstance(sources, (str, Path)) or is_labeled_source(sources):
            self.sources: tuple[SkillSource, ...] = (sources,)
        else:
            self.sources = tuple(sources)
        self.source_paths = tuple(source_path(source) for source in self.sources)
        self.source_labels = tuple(source_label(source) for source in self.sources)

    def discover(self) -> SkillIndex:
        """扫描所有来源目录，后面的来源覆盖前面的同名 skill。"""
        skills: dict[str, SkillDefinition] = {}
        errors: list[str] = []

        for current_source_path in self.source_paths:
            source_skills, source_errors = self._discover_source(current_source_path)
            errors.extend(source_errors)
            for skill in source_skills:
                skills[skill.name] = skill

        return SkillIndex(
            skills=skills,
            load_errors=tuple(errors),
        )

    def _discover_source(self, current_source_path: Path) -> tuple[list[SkillDefinition], list[str]]:
        """扫描单个来源目录。"""
        skills: list[SkillDefinition] = []
        errors: list[str] = []

        if not current_source_path.exists():
            errors.append(f"skill 来源目录不存在: {current_source_path}")
            return skills, errors
        if not current_source_path.is_dir():
            errors.append(f"skill 来源不是目录: {current_source_path}")
            return skills, errors

        for skill_dir in sorted(current_source_path.iterdir(), key=lambda item: item.name):
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.is_file():
                continue
            try:
                skills.append(parse_skill_file(skill_file))
            except Exception as exc:
                message = f"加载 {skill_file} 失败: {exc}"
                logger.warning("%s", message)
                errors.append(message)

        return skills, errors
