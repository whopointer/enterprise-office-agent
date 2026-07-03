"""从自然语言中提取常见结构化字段的轻量兜底。"""

from __future__ import annotations

import re


def extract_fields_from_query(user_query: str) -> dict[str, str]:
    """从中文自然语言中提取 filename / template_name 等常用字段。"""
    fields: dict[str, str] = {}

    filename = _match_first(
        user_query,
        [
            r"文件名(?:是|为|叫)\s*([A-Za-z0-9_.\-/\\\u4e00-\u9fff]+)",
            r"文件名\s+([A-Za-z0-9_.\-/\\\u4e00-\u9fff]+)",
            r"输出(?:到|为)?\s*([A-Za-z0-9_.\-/\\\u4e00-\u9fff]+\.docx)",
            r"([A-Za-z0-9_.\-/\\\u4e00-\u9fff]+\.docx)",
        ],
    )
    if filename:
        fields["filename"] = filename

    template_name = _match_first(
        user_query,
        [
            r"模板(?:名称|名)?(?:是|为|叫)\s*([A-Za-z0-9_.\-/\\\u4e00-\u9fff]+)",
            r"模板(?:名称|名)?\s+([A-Za-z0-9_.\-/\\\u4e00-\u9fff]+)",
            r"template(?:_name)?(?:=|:|\s+is\s+)?\s*([A-Za-z0-9_.\-/\\]+)",
        ],
    )
    if template_name:
        fields["template_name"] = template_name

    title = _match_first(
        user_query,
        [
            r"标题(?:是|为|叫)\s*([A-Za-z0-9_.\-/\\\u4e00-\u9fff ]+)",
            r"title(?:=|:|\s+is\s+)\s*([A-Za-z0-9_.\-/\\ ]+)",
        ],
    )
    if title:
        fields["title"] = title

    output_path = _match_first(
        user_query,
        [
            r"输出路径(?:是|为|到)?\s*([A-Za-z0-9_.\-/\\\u4e00-\u9fff ]+)",
            r"保存(?:到|为)\s*([A-Za-z0-9_.\-/\\\u4e00-\u9fff ]+)",
            r"output_path(?:=|:|\s+is\s+)\s*([A-Za-z0-9_.\-/\\ ]+)",
        ],
    )
    if output_path:
        fields["output_path"] = output_path

    date = _match_first(
        user_query,
        [
            r"日期(?:是|为)?\s*(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?)",
            r"date(?:=|:|\s+is\s+)\s*(\d{4}-\d{1,2}-\d{1,2})",
        ],
    )
    if date:
        fields["date"] = date

    report_type = _match_first(
        user_query,
        [
            r"报告类型(?:是|为|叫)\s*([A-Za-z0-9_.\-/\\\u4e00-\u9fff]+)",
            r"report_type(?:=|:|\s+is\s+)\s*([A-Za-z0-9_.\-/\\]+)",
        ],
    )
    if report_type:
        fields["report_type"] = report_type

    output_format = _match_first(
        user_query,
        [
            r"格式(?:是|为)?\s*(docx|pdf|markdown|md|html|json)",
            r"format(?:=|:|\s+is\s+)\s*(docx|pdf|markdown|md|html|json)",
        ],
    )
    if output_format:
        fields["format"] = output_format

    language = _match_first(
        user_query,
        [
            r"语言(?:是|为)?\s*(中文|英文|中英双语|Chinese|English)",
            r"language(?:=|:|\s+is\s+)\s*(Chinese|English|zh|en)",
        ],
    )
    if language:
        fields["language"] = language

    return fields


def _match_first(text: str, patterns: list[str]) -> str | None:
    """返回第一个匹配分组。"""
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).strip("，。；;,. ")
            if value and value not in {"是", "为", "叫", "名", "名称"}:
                return value
    return None
