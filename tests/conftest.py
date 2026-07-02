"""pytest 全局配置：测试结束后自动落盘 JSON + Markdown 报告到 test-results/ 目录。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json


OUTPUT_DIR = Path("test-results")


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """测试全结束后从 terminalreporter.stats 提取结果并落盘。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    stats = terminalreporter.stats
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
            items.append({
                "nodeid": nodeid,
                "outcome": status,
                "duration": round(duration, 4),
            })

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    summary = {
        "timestamp": timestamp,
        "exit_code": exitstatus,
        "total": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "error": error,
        "pass_rate": round(passed / total, 4) if total > 0 else 0,
        "duration_seconds": round(getattr(terminalreporter, "_sessionstarttime", 0), 2),
    }

    # JSON
    json_path = OUTPUT_DIR / "test-report.json"
    json_path.write_text(
        json.dumps({"summary": summary, "cases": items}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Markdown
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

    terminalreporter.write_sep("=", f"报告已落盘: {json_path}", bold=True)
    terminalreporter.write_sep("=", f"报告已落盘: {md_path}", bold=True)
