"""SKILL.md DSL 解析逻辑 — 对齐官方格式（name + description + allowed-tools + body）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import logging
import re

import yaml

from .constants import (
    MAX_SKILL_COMPATIBILITY_LENGTH,
    MAX_SKILL_DESCRIPTION_LENGTH,
    MAX_SKILL_FILE_SIZE,
    MAX_SKILL_NAME_LENGTH,
)
from .models import SkillDefinition

logger = logging.getLogger(__name__)


def parse_skill_file(skill_file: str | Path) -> SkillDefinition:
    """解析单个 SKILL.md，返回纯数据 SkillDefinition。"""
    path = Path(skill_file).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"SKILL.md 不存在: {path}")

    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        raise ValueError(f"SKILL.md 编码不是 UTF-8: {path}") from e

    if len(content.encode("utf-8")) > MAX_SKILL_FILE_SIZE:
        raise ValueError(f"SKILL.md 超过大小限制: {path}")

    split = _split_frontmatter(content)
    if split is None:
        raise ValueError(f"SKILL.md 缺少合法 frontmatter: {path}")
    frontmatter, body = split

    name = str(frontmatter.get("name", "")).strip()
    description = str(frontmatter.get("description", "")).strip()
    _validate_skill_name(name)
    _validate_skill_directory_name(name, path.parent.name)

    if not description:
        raise ValueError("缺少 description")
    if len(description) > MAX_SKILL_DESCRIPTION_LENGTH:
        description = description[:MAX_SKILL_DESCRIPTION_LENGTH]

    allowed_tools = _parse_allowed_tools(frontmatter.get("allowed-tools"))

    compatibility = str(frontmatter.get("compatibility", "")).strip() or None
    if compatibility and len(compatibility) > MAX_SKILL_COMPATIBILITY_LENGTH:
        compatibility = compatibility[:MAX_SKILL_COMPATIBILITY_LENGTH]

    return SkillDefinition(
        name=name,
        description=description,
        path=str(path),
        directory=str(path.parent),
        body=body.strip(),
        allowed_tools=allowed_tools,
        metadata=_validate_metadata(frontmatter.get("metadata")),
        license=str(frontmatter.get("license", "")).strip() or None,
        compatibility=compatibility,
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


def _validate_skill_directory_name(name: str, directory_name: str) -> None:
    """skill name 应等于所在目录名，不匹配时 warn 但不阻断加载。"""
    if name != directory_name:
        logger.warning(
            "skill name '%s' 与目录名 '%s' 不一致，建议保持一致",
            name, directory_name,
        )


def _parse_allowed_tools(value: Any) -> tuple[str, ...]:
    """解析 allowed-tools —— 接受 string（空格分隔）或 list。"""
    if isinstance(value, str):
        return tuple(t.strip(",").strip() for t in value.split() if t.strip(",").strip())
    if isinstance(value, (list, tuple, set)):
        return tuple(str(t).strip() for t in value if str(t).strip())
    if value is not None:
        logger.warning("allowed-tools 必须是 string 或 list 类型，已忽略")
    return ()


def _validate_metadata(value: Any) -> dict[str, str]:
    """仅接受 dict 类型的 metadata，value 强制转 str。"""
    if isinstance(value, dict):
        return {str(k): str(v) for k, v in value.items()}
    if value is not None:
        logger.warning("metadata 必须是 dict 类型，已忽略")
    return {}
