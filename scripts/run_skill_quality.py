"""生成 Skill 系统基础设施质量报告。"""

from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys
import time
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _skill import FileSkillDiscovery
from agent.field_extractor import extract_fields_from_query
from core.token_tracker import TokenTracker
from llm.skill_router import OpenAIChatSkillRouter


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


class _NoCallCompletions:
    def create(self, **_kwargs):
        raise RuntimeError("质量报告脚本不调用真实 LLM")


class _NoCallChat:
    completions = _NoCallCompletions()


class _NoCallClient:
    chat = _NoCallChat()


def main() -> None:
    """命令行入口。"""
    parser = argparse.ArgumentParser(description="生成 Skill 系统质量指标报告")
    parser.add_argument("--skills-dir", default="skills", help="skill 根目录")
    parser.add_argument("--output-dir", default="test-results", help="报告输出目录")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    skills_dir = _resolve_path(repo_root, args.skills_dir)
    output_dir = _resolve_path(repo_root, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    start = time.perf_counter()
    index = FileSkillDiscovery(skills_dir).discover()
    discovery_ms = (time.perf_counter() - start) * 1000

    tracker = TokenTracker()
    inventory = _inventory_report(index, skills_dir, discovery_ms)
    prompt_budget = _prompt_budget_report(index, tracker)
    field_quality = _field_quality_report()
    summary = {
        "inventory": inventory,
        "prompt_budget": prompt_budget,
        "field_quality": field_quality,
    }

    (output_dir / "skill-quality-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "skill-quality-summary.md").write_text(
        _format_markdown(summary),
        encoding="utf-8",
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))


def _resolve_path(repo_root: Path, raw: str) -> Path:
    """解析命令行路径。"""
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    return repo_root / path


def _inventory_report(index, skills_dir: Path, discovery_ms: float) -> dict[str, Any]:
    """统计真实 skill 库存。"""
    skills = index.list_skills()
    resource_counts = {"references": 0, "assets": 0, "scripts": 0}
    body_lengths = []
    description_lengths = []

    for skill in skills:
        skill_dir = Path(skill.directory)
        body_lengths.append(len(skill.body))
        description_lengths.append(len(skill.description))
        for name in resource_counts:
            resource_dir = skill_dir / name
            if resource_dir.is_dir() and any(resource_dir.iterdir()):
                resource_counts[name] += 1

    return {
        "skills_dir": str(skills_dir),
        "skill_count": len(skills),
        "load_error_count": len(index.load_errors),
        "load_errors": list(index.load_errors),
        "discovery_ms": round(discovery_ms, 2),
        "resource_counts": resource_counts,
        "description_length": _length_stats(description_lengths),
        "body_length": _length_stats(body_lengths),
    }


def _prompt_budget_report(index, tracker: TokenTracker) -> dict[str, Any]:
    """统计渐进披露 prompt 成本。"""
    router = OpenAIChatSkillRouter(index, model="quality-no-call", client=_NoCallClient())
    route_prompt = router._build_system_prompt()
    route_tokens = tracker.count(route_prompt)
    body_tokens = sum(tracker.count(skill.body) for skill in index.list_skills())
    description_tokens = sum(tracker.count(skill.description) for skill in index.list_skills())
    total_if_full_loaded = route_tokens + body_tokens
    saved_rate = 1.0
    if total_if_full_loaded > 0:
        saved_rate = 1 - (route_tokens / total_if_full_loaded)

    return {
        "route_prompt_chars": len(route_prompt),
        "route_prompt_tokens": route_tokens,
        "description_tokens": description_tokens,
        "body_tokens": body_tokens,
        "total_if_full_loaded_tokens": total_if_full_loaded,
        "progressive_disclosure_saved_rate": round(saved_rate, 4),
    }


def _field_quality_report() -> dict[str, Any]:
    """统计字段抽取质量。"""
    true_positive = 0
    predicted_total = 0
    expected_total = 0
    exact_match_count = 0
    details = []

    for query, expected in FIELD_CASES:
        actual = extract_fields_from_query(query)
        predicted_total += len(actual)
        expected_total += len(expected)
        true_positive += sum(1 for key, value in actual.items() if expected.get(key) == value)
        exact = actual == expected
        exact_match_count += 1 if exact else 0
        details.append({"query": query, "expected": expected, "actual": actual, "exact_match": exact})

    return {
        "case_count": len(FIELD_CASES),
        "exact_match_rate": _safe_rate(exact_match_count, len(FIELD_CASES)),
        "precision": _safe_rate(true_positive, predicted_total),
        "recall": _safe_rate(true_positive, expected_total),
        "details": details,
    }


def _length_stats(values: list[int]) -> dict[str, float | int]:
    """计算长度统计。"""
    if not values:
        return {"min": 0, "max": 0, "avg": 0}
    return {
        "min": min(values),
        "max": max(values),
        "avg": round(sum(values) / len(values), 1),
    }


def _safe_rate(numerator: int | float, denominator: int | float) -> float:
    """安全计算比例。"""
    if denominator == 0:
        return 1.0
    return round(float(numerator) / float(denominator), 4)


def _format_markdown(summary: dict[str, Any]) -> str:
    """生成 Markdown 报告。"""
    inventory = summary["inventory"]
    prompt = summary["prompt_budget"]
    fields = summary["field_quality"]

    lines = [
        "# Skill 系统质量报告",
        "",
        "## 库存",
        "",
        f"- Skill 数量: {inventory['skill_count']}",
        f"- 加载错误数: {inventory['load_error_count']}",
        f"- Discovery 耗时: {inventory['discovery_ms']} ms",
        f"- references 目录数: {inventory['resource_counts']['references']}",
        f"- assets 目录数: {inventory['resource_counts']['assets']}",
        f"- scripts 目录数: {inventory['resource_counts']['scripts']}",
        "",
        "## Prompt 成本",
        "",
        f"- 路由 prompt token: {prompt['route_prompt_tokens']}",
        f"- description token: {prompt['description_tokens']}",
        f"- body token: {prompt['body_tokens']}",
        f"- 渐进披露节省率: {prompt['progressive_disclosure_saved_rate']:.1%}",
        "",
        "## 字段抽取",
        "",
        f"- 用例数: {fields['case_count']}",
        f"- 完全匹配率: {fields['exact_match_rate']:.1%}",
        f"- Precision: {fields['precision']:.1%}",
        f"- Recall: {fields['recall']:.1%}",
        "",
    ]
    if inventory["load_errors"]:
        lines.extend(["## 加载错误", ""])
        for error in inventory["load_errors"]:
            lines.append(f"- {error}")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
