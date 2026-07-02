"""从自然语言中提取常见红线字段的轻量兜底。"""

from __future__ import annotations

import re


def extract_fields_from_query(user_query: str) -> dict[str, str]:
    """从中文自然语言中提取 filename / template_name 等常用字段。"""
    fields: dict[str, str] = {}

    filename = _match_first(
        user_query,
        [
            r"文件名(?:是|为|叫)?\s*([A-Za-z0-9_.\-/\\\u4e00-\u9fff]+)",
            r"输出(?:到|为)?\s*([A-Za-z0-9_.\-/\\\u4e00-\u9fff]+\.docx)",
            r"([A-Za-z0-9_.\-/\\\u4e00-\u9fff]+\.docx)",
        ],
    )
    if filename:
        fields["filename"] = filename

    template_name = _match_first(
        user_query,
        [
            r"模板(?:名|名称)?(?:是|为|叫)?\s*([A-Za-z0-9_.\-/\\\u4e00-\u9fff]+)",
            r"template(?:_name)?(?:=|:|\s+is\s+)?\s*([A-Za-z0-9_.\-/\\]+)",
        ],
    )
    if template_name:
        fields["template_name"] = template_name

    return fields


def _match_first(text: str, patterns: list[str]) -> str | None:
    """返回第一个匹配分组。"""
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip("，。；;,. ")
    return None
