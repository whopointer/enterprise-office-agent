"""Skill 机制内部复用的小工具函数。"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import re

from .constants import MAX_LOAD_WARNING_LENGTH, WARNING_TRUNCATION_SUFFIX
from .models import SkillSource


def is_labeled_source(value: Any) -> bool:
    """判断对象是否是 (路径, 标签) 形式的单个来源。"""
    return (
        isinstance(value, tuple)
        and len(value) == 2
        and isinstance(value[0], (str, Path))
        and isinstance(value[1], str)
    )


def source_path(source: SkillSource) -> Path:
    """提取来源目录路径。"""
    if is_labeled_source(source):
        return Path(source[0]).expanduser()
    if isinstance(source, tuple):
        raise TypeError(f"skill 来源必须是路径或 (路径, 标签)，实际为: {source!r}")
    return Path(source).expanduser()


def source_label(source: SkillSource) -> str:
    """生成来源在 prompt 中展示的标签。"""
    if is_labeled_source(source):
        return str(source[1])

    path = source_path(source)
    leaf = path.name or "未命名"
    if leaf.lower() == "skills" and path.parent.name:
        return path.parent.name.strip(".").replace("_", " ").replace("-", " ").title()
    if leaf.lower() == "built_in_skills":
        return "内置"
    return leaf


def truncate_warning(message: str) -> str:
    """限制加载告警长度，避免把大段错误注入 prompt。"""
    if len(message) <= MAX_LOAD_WARNING_LENGTH:
        return message
    keep = MAX_LOAD_WARNING_LENGTH - len(WARNING_TRUNCATION_SUFFIX)
    return f"{message[:keep]}{WARNING_TRUNCATION_SUFFIX}"


def normalize_string_list(value: Any) -> tuple[str, ...]:
    """把 YAML 字段规整为字符串元组。"""
    if value is None:
        return ()
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return (str(value).strip(),) if str(value).strip() else ()


def normalize_metadata(value: Any) -> dict[str, str]:
    """把 metadata 规整成字符串键值对。"""
    if not isinstance(value, dict):
        return {}
    return {str(key): str(val) for key, val in value.items()}


def extract_match_terms(text: str) -> tuple[str, ...]:
    """提取用于匹配的英文 token 和中文片段。"""
    return tuple(re.findall(r"[a-z0-9][a-z0-9-]*|[\u4e00-\u9fff]{2,}", text.lower()))


def is_ascii_term(term: str) -> bool:
    """判断匹配词是否为英文/数字 token。"""
    return all(ord(char) < 128 for char in term)


def term_matches_query(term: str, query_terms: tuple[str, ...]) -> bool:
    """判断一个词是否命中用户 query。"""
    if is_ascii_term(term):
        return term in query_terms
    return any(term in query_term or query_term in term for query_term in query_terms if not is_ascii_term(query_term))


def keyword_matches_query(keyword: str, query: str, query_terms: tuple[str, ...]) -> bool:
    """判断 trigger keyword 是否命中用户 query。"""
    normalized = keyword.lower().strip()
    if not normalized:
        return False
    if re.fullmatch(r"[a-z0-9][a-z0-9-]*", normalized):
        return normalized in query_terms
    return normalized in query


def safe_rate(numerator: int | float, denominator: int | float) -> float:
    """安全计算比例，分母为 0 时返回 1.0。"""
    if denominator == 0:
        return 1.0
    return float(numerator) / float(denominator)


def average(values: list[float]) -> float:
    """计算平均值，空列表返回 0。"""
    if not values:
        return 0.0
    return sum(values) / len(values)
