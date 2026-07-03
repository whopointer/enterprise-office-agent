"""pytest 全局配置：测试结束后自动落盘 JSON + Markdown 报告 + 量化指标。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json

import pytest

OUTPUT_DIR = Path("test-results")


# ---------------------------------------------------------------------------
# 全局 RuntimeCollector — 测试执行时填充，session 结束时落盘
# ---------------------------------------------------------------------------

_runtime_collector: object = None


def get_runtime_collector():
    """获取全局 RuntimeCollector 单例。"""
    global _runtime_collector
    if _runtime_collector is None:
        from core.runtime_metrics import RuntimeCollector
        _runtime_collector = RuntimeCollector()
    return _runtime_collector


@pytest.fixture(scope="session")
def runtime_collector():
    """session 级 fixture：所有测试共享同一个 RuntimeCollector。"""
    return get_runtime_collector()


# ---------------------------------------------------------------------------
# Session 结束：写入测试汇总 + 量化报告
# ---------------------------------------------------------------------------

def pytest_sessionfinish(session, exitstatus):
    """测试全结束后落盘。"""
    if session.config.option.collectonly:
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # ---- 1. 测试结果汇总 ----
    tr = session.config.pluginmanager.get_plugin("terminalreporter")
    if tr is None:
        return

    stats = getattr(tr, "stats", {})
    passed = len(stats.get("passed", []))
    failed = len(stats.get("failed", []))
    skipped = len(stats.get("skipped", []))
    error = len(stats.get("error", []))
    total = passed + failed + skipped + error

    items: list[dict] = []
    for status in ("passed", "failed", "skipped", "error"):
        for report in stats.get(status, []):
            nodeid = getattr(report, "nodeid", str(report))
            duration = getattr(report, "duration", 0)
            items.append({"nodeid": nodeid, "outcome": status, "duration": round(duration, 4)})

    summary = {
        "timestamp": timestamp,
        "exit_code": exitstatus,
        "total": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "error": error,
        "pass_rate": round(passed / total, 4) if total > 0 else 0,
    }

    json_path = OUTPUT_DIR / "test-report.json"
    json_path.write_text(json.dumps({"summary": summary, "cases": items}, ensure_ascii=False, indent=2), encoding="utf-8")

    md_path = OUTPUT_DIR / "test-report.md"
    md_lines = [
        "# 测试报告",
        "",
        f"**时间**: {timestamp}",
        f"**总用例**: {total}  |  通过: {passed}  |  失败: {failed}  |  跳过: {skipped}  |  错误: {error}",
        f"**通过率**: {summary['pass_rate']:.1%}",
        f"**退出码**: {exitstatus}",
        "",
        *_related_report_lines(OUTPUT_DIR),
        "## 用例明细",
        "",
        "| 用例 | 结果 | 耗时(s) |",
        "|------|------|---------|",
    ]
    for item in items:
        short = item["nodeid"].split("::")[-1] if "::" in item["nodeid"] else item["nodeid"]
        emoji = {"passed": "✅", "failed": "❌", "skipped": "⏭️", "error": "⚠️"}.get(item["outcome"], "❓")
        md_lines.append(f"| {short} | {emoji} {item['outcome']} | {item['duration']:.3f} |")
    if not items:
        md_lines.append("| - | - | - |")
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    # ---- 2. 量化指标报告 ----
    if _runtime_collector is not None:
        qj, qm = _runtime_collector.write_report(OUTPUT_DIR)
        tr.write_sep("=", f"量化报告: {qj}", bold=True)
        tr.write_sep("=", f"量化报告: {qm}", bold=True)

    tr.write_sep("=", f"测试汇总: {json_path}", bold=True)
    tr.write_sep("=", f"测试汇总: {md_path}", bold=True)


def _related_report_lines(output_dir: Path) -> list[str]:
    """生成已存在评测报告的摘要入口，避免不同统计口径混淆。"""
    lines: list[str] = ["## 相关评测报告", ""]
    added = False

    routing_path = output_dir / "routing-eval-report.json"
    if routing_path.exists():
        routing = _read_json(routing_path)
        summary = routing.get("summary", {}) if isinstance(routing, dict) else {}
        cm = summary.get("confusion_matrix", {}) if isinstance(summary, dict) else {}
        lines.extend([
            "- `routing-eval-report.md`: 真实 LLM 大样本路由评测。",
            f"  样本: {summary.get('total_cases', 0)}，通过: {summary.get('passed_cases', 0)}，Case Accuracy: {summary.get('case_accuracy', 0):.1%}。",
            f"  混淆矩阵: TP={cm.get('TP', 0)} / TN={cm.get('TN', 0)} / FP={cm.get('FP', 0)} / FN={cm.get('FN', 0)}。",
            "",
        ])
        added = True

    quality_path = output_dir / "skill-quality-summary.json"
    if quality_path.exists():
        quality = _read_json(quality_path)
        inventory = quality.get("inventory", {}) if isinstance(quality, dict) else {}
        prompt_budget = quality.get("prompt_budget", {}) if isinstance(quality, dict) else {}
        field_quality = quality.get("field_quality", {}) if isinstance(quality, dict) else {}
        lines.extend([
            "- `skill-quality-summary.md`: skill 盘点、prompt 预算、字段抽取质量摘要。",
            f"  Skills: {inventory.get('skill_count', 0)}，Load errors: {inventory.get('load_error_count', 0)}，路由 prompt tokens: {prompt_budget.get('route_prompt_tokens', 0)}。",
            f"  字段抽取样本: {field_quality.get('case_count', 0)}，Exact match: {field_quality.get('exact_match_rate', 0):.1%}。",
            "",
        ])
        added = True

    if not added:
        lines.extend([
            "- 暂无额外评测报告。可运行 `python3 scripts/run_routing_eval.py --output-dir test-results` 和 `python3 scripts/run_skill_quality.py --output-dir test-results` 生成。",
            "",
        ])

    return lines


def _read_json(path: Path) -> dict:
    """读取 JSON 报告，失败时返回空 dict。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}
