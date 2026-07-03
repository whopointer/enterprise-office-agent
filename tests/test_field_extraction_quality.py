"""字段抽取质量的参数化测试。"""

from __future__ import annotations

from agent.field_extractor import extract_fields_from_query


FIELD_CASES = [
    ("文件名是 weekly.docx，帮我生成报告", {"filename": "weekly.docx"}),
    ("输出为 reports/q2.docx", {"filename": "reports/q2.docx"}),
    ("请生成 项目周报.docx", {"filename": "项目周报.docx"}),
    ("文件名 output-final.docx", {"filename": "output-final.docx"}),
    ("生成 report_v2.docx", {"filename": "report_v2.docx"}),
    ("输出到 合同终版.docx", {"filename": "合同终版.docx"}),
    ("请保存为 archive/summary.docx", {"filename": "archive/summary.docx", "output_path": "archive/summary.docx"}),
    ("文件名叫 sales-2026.docx", {"filename": "sales-2026.docx"}),
    ("模板名称是 standard-report", {"template_name": "standard-report"}),
    ("template_name: finance-v1", {"template_name": "finance-v1"}),
    ("template=weekly", {"template_name": "weekly"}),
    ("模板名为 legal-template", {"template_name": "legal-template"}),
    ("模板叫 annual-template", {"template_name": "annual-template"}),
    ("模板名称 enterprise-v2", {"template_name": "enterprise-v2"}),
    ("template_name is board-pack", {"template_name": "board-pack"}),
    ("标题是 项目周报", {"title": "项目周报"}),
    ("标题为 Q2经营分析", {"title": "Q2经营分析"}),
    ("标题叫 客户拜访纪要", {"title": "客户拜访纪要"}),
    ("title: Weekly Report", {"title": "Weekly Report"}),
    ("title is Board Pack", {"title": "Board Pack"}),
    ("输出路径是 reports/weekly.md", {"output_path": "reports/weekly.md"}),
    ("输出路径为 artifacts/q2.pdf", {"output_path": "artifacts/q2.pdf"}),
    ("输出路径 reports/final.html", {"output_path": "reports/final.html"}),
    ("保存到 output/monthly.pdf", {"output_path": "output/monthly.pdf"}),
    ("保存为 archive/result.json", {"output_path": "archive/result.json"}),
    ("output_path: dist/report.docx", {"filename": "dist/report.docx", "output_path": "dist/report.docx"}),
    ("output_path is build/final.pdf", {"output_path": "build/final.pdf"}),
    ("日期是 2026-07-03", {"date": "2026-07-03"}),
    ("日期为 2026/7/3", {"date": "2026/7/3"}),
    ("日期 2026年07月03日", {"date": "2026年07月03日"}),
    ("date: 2026-12-31", {"date": "2026-12-31"}),
    ("date is 2027-1-2", {"date": "2027-1-2"}),
    ("报告类型是 周报", {"report_type": "周报"}),
    ("报告类型为 季报", {"report_type": "季报"}),
    ("报告类型叫 验收报告", {"report_type": "验收报告"}),
    ("report_type: weekly", {"report_type": "weekly"}),
    ("report_type is qbr", {"report_type": "qbr"}),
    ("格式是 docx", {"format": "docx"}),
    ("格式为 pdf", {"format": "pdf"}),
    ("格式 markdown", {"format": "markdown"}),
    ("format: html", {"format": "html"}),
    ("format is json", {"format": "json"}),
    ("语言是中文", {"language": "中文"}),
    ("语言为 英文", {"language": "英文"}),
    ("语言 中英双语", {"language": "中英双语"}),
    ("language: Chinese", {"language": "Chinese"}),
    ("language is en", {"language": "en"}),
    ("文件名为 q3.docx，模板叫 annual-template", {"filename": "q3.docx", "template_name": "annual-template"}),
    (
        "文件名是 board.docx，标题为 董事会报告，日期是 2026-07-03，格式为 docx",
        {"filename": "board.docx", "title": "董事会报告", "date": "2026-07-03", "format": "docx"},
    ),
    (
        "模板名称是 finance-v1，报告类型为 季报，语言为 中文，保存到 out/q2.pdf",
        {"template_name": "finance-v1", "report_type": "季报", "language": "中文", "output_path": "out/q2.pdf"},
    ),
]


def test_field_extractor_exact_match_cases() -> None:
    """已支持的 filename/template_name 表达应完全匹配。"""
    assert len(FIELD_CASES) == 50
    for query, expected in FIELD_CASES:
        assert extract_fields_from_query(query) == expected


def test_field_extractor_quality_metrics_are_computable() -> None:
    """计算字段级 precision/recall，作为后续报告脚本口径。"""
    true_positive = 0
    predicted_total = 0
    expected_total = 0

    for query, expected in FIELD_CASES:
        actual = extract_fields_from_query(query)
        predicted_total += len(actual)
        expected_total += len(expected)
        true_positive += sum(1 for key, value in actual.items() if expected.get(key) == value)

    precision = true_positive / predicted_total
    recall = true_positive / expected_total

    assert precision == 1.0
    assert recall == 1.0


def test_field_extractor_handles_negative_cases() -> None:
    """无明确字段时应返回空 dict，避免把普通文本误抽成字段。"""
    for query in ("", "帮我写一段 Python 代码", "文件名是", "模板名称为", "标题是", "日期为", "格式是", "语言为"):
        assert extract_fields_from_query(query) == {}
