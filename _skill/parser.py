"""SKILL.md DSL 解析逻辑 — 对齐官方格式（name + description + allowed-tools + body）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import re

import yaml

from .constants import MAX_SKILL_DESCRIPTION_LENGTH, MAX_SKILL_FILE_SIZE, MAX_SKILL_NAME_LENGTH
from .models import SkillDefinition
from .utils import normalize_metadata, normalize_string_list


def parse_skill_file(skill_file: str | Path) -> SkillDefinition:
    """解析单个 SKILL.md，返回纯数据 SkillDefinition。"""
    path = Path(skill_file).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"SKILL.md 不存在: {path}")

    content = path.read_text(encoding="utf-8")
    if len(content.encode("utf-8")) > MAX_SKILL_FILE_SIZE:
        raise ValueError(f"SKILL.md 超过大小限制: {path}")

    split = _split_frontmatter(content)
    if split is None:
        raise ValueError(f"SKILL.md 缺少合法 frontmatter: {path}")
    frontmatter, body = split

    name = str(frontmatter.get("name", "")).strip()
    description = str(frontmatter.get("description", "")).strip()
    _validate_skill_name(name)

    if not description:
        raise ValueError("缺少 description")
    if len(description) > MAX_SKILL_DESCRIPTION_LENGTH:
        description = description[:MAX_SKILL_DESCRIPTION_LENGTH]

    allowed_tools = normalize_string_list(frontmatter.get("allowed-tools"))

    return SkillDefinition(
        name=name,
        description=description,
        path=str(path),
        directory=str(path.parent),
        body=body.strip(),
        allowed_tools=allowed_tools,
        metadata=normalize_metadata(frontmatter.get("metadata")),
        license=str(frontmatter.get("license", "")).strip() or None,
        compatibility=str(frontmatter.get("compatibility", "")).strip() or None,
    )


def _split_frontmatter(content: str) -> tuple[dict[str, Any], str] | None:
    """拆分 SKILL.md 的 YAML frontmatter 与正文。"""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?", content, re.DOTALL)
    if not match:
        return None

    raw_frontmatter = match.group(1)
    body = content[match.end() :]
    parsed = yaml.safe_load(raw_frontmatter) or {}
    if not isinstance(parsed, dict):
        raise ValueError("frontmatter 必须是 YAML mapping")
    return parsed, body


def _validate_skill_name(name: str) -> None:
    """校验 skill 名称的基本格式。"""
    if not name:
        raise ValueError("缺少 name")
    if len(name) > MAX_SKILL_NAME_LENGTH:
        raise ValueError("name 超过 64 个字符")
    if name.startswith("-") or name.endswith("-") or "--" in name:
        raise ValueError("name 不能以连字符开头或结尾，也不能包含连续连字符")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
        raise ValueError("name 只能包含小写字母、数字和连字符")
