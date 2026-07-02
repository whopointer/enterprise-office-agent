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
