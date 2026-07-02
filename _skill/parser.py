"""SKILL.md DSL 解析逻辑。"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import re

import yaml

from .constants import MAX_SKILL_DESCRIPTION_LENGTH, MAX_SKILL_FILE_SIZE, MAX_SKILL_NAME_LENGTH
from .models import RedLineRule, SkillAsset, SkillDefinition, SkillMetricsSpec, TokenEstimate
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

    skill_dir = path.parent
    triggers = frontmatter.get("triggers", {})
    if not isinstance(triggers, dict):
        triggers = {}

    return SkillDefinition(
        name=name,
        description=description,
        path=str(path),
        directory=str(skill_dir),
        body=body.strip(),
        triggers=triggers,
        red_lines=_parse_red_lines(frontmatter.get("red_lines")),
        references=normalize_string_list(frontmatter.get("references")),
        assets=_parse_assets(frontmatter.get("assets"), skill_dir),
        metrics=_parse_metrics(frontmatter.get("metrics")),
        token_estimate=_parse_token_estimate(frontmatter.get("token_estimate")),
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


def _parse_red_lines(value: Any) -> tuple[RedLineRule, ...]:
    """解析红线 DSL。"""
    rules: list[RedLineRule] = []
    if not value:
        return ()

    if isinstance(value, dict) and "required_fields" in value:
        for field_name in normalize_string_list(value.get("required_fields")):
            rules.append(RedLineRule(field=field_name, message=f"缺少必填字段: {field_name}"))
        return tuple(rules)

    if not isinstance(value, list):
        return ()

    for item in value:
        if not isinstance(item, dict):
            continue
        field_name = str(item.get("field", "")).strip()
        if not field_name:
            continue
        message = str(item.get("message", "")).strip() or f"缺少必填字段: {field_name}"
        rules.append(RedLineRule(field=field_name, message=message))
    return tuple(rules)


def _parse_assets(value: Any, skill_dir: Path) -> tuple[SkillAsset, ...]:
    """解析 asset DSL 并解析本地绝对路径。"""
    assets: list[SkillAsset] = []
    if not value:
        return ()

    raw_assets = value if isinstance(value, list) else [value]
    for item in raw_assets:
        if isinstance(item, str):
            asset_path = item.strip()
            asset_type = "file"
            description = ""
        elif isinstance(item, dict):
            asset_path = str(item.get("path", "")).strip()
            asset_type = str(item.get("type", "file")).strip() or "file"
            description = str(item.get("description", "")).strip()
        else:
            continue

        if not asset_path:
            continue

        resolved = (skill_dir / asset_path).resolve()
        assets.append(
            SkillAsset(
                path=asset_path,
                type=asset_type,
                description=description,
                resolved_path=str(resolved),
                exists=resolved.exists(),
            )
        )
    return tuple(assets)


def _parse_metrics(value: Any) -> SkillMetricsSpec:
    """解析量化评估期望。"""
    if not isinstance(value, dict):
        return SkillMetricsSpec()
    expected_activation = value.get("expected_activation")
    if not isinstance(expected_activation, bool):
        expected_activation = None
    return SkillMetricsSpec(
        expected_skill=str(value.get("expected_skill", "")).strip() or None,
        expected_activation=expected_activation,
        expected_references=normalize_string_list(value.get("expected_references")),
        expected_assets=normalize_string_list(value.get("expected_assets")),
    )


def _parse_token_estimate(value: Any) -> TokenEstimate:
    """解析 token 估算配置。"""
    if not isinstance(value, dict):
        return TokenEstimate()
    return TokenEstimate(
        system_prompt=max(0, int(value.get("system_prompt", 0) or 0)),
        per_reference=max(0, int(value.get("per_reference", 0) or 0)),
        per_asset=max(0, int(value.get("per_asset", 0) or 0)),
    )


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
