"""轻量运行时量化指标采集 — 统计 token 消耗、延迟、适配器成功率、混淆矩阵。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json

from _skill.models import ExecutionMetrics, TokenMetrics
from _skill.utils import safe_rate, average


@dataclass
class RuntimeMetrics:
    """一次执行的运行时指标快照。"""

    skill_name: str
    adapter_name: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_ms: float
    success: bool
    token_source: str


@dataclass
class EvalRecord:
    """一次 LLM 路由结果的评估记录。"""

    query: str
    expected_skill: str | None
    actual_skill: str | None
    expected_activation: bool
    actual_activation: bool
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    token_source: str | None = None


@dataclass
class RuntimeCollector:
    """跨用例采集执行期量化指标 + 路由准确度。"""

    records: list[RuntimeMetrics] = field(default_factory=list)
    eval_records: list[EvalRecord] = field(default_factory=list)

    # ---- 执行指标 ----

    def record(self, skill_name: str, metrics: ExecutionMetrics) -> None:
        """记录一次执行。"""
        self.records.append(RuntimeMetrics(
            skill_name=skill_name,
            adapter_name=metrics.adapter_name,
            input_tokens=metrics.token_metrics.input_tokens,
            output_tokens=metrics.token_metrics.output_tokens,
            total_tokens=metrics.token_metrics.total_tokens,
            latency_ms=metrics.latency_ms,
            success=metrics.execution_success,
            token_source=metrics.token_metrics.source,
        ))

    # ---- 路由准确度 ----

    def record_routing(
        self, query: str, expected_skill: str | None, actual_skill: str | None,
        expected_activation: bool, actual_activation: bool,
        token_metrics: TokenMetrics | None = None,
    ) -> None:
        """记录一次 LLM 路由决策。"""
        self.eval_records.append(EvalRecord(
            query=query,
            expected_skill=expected_skill,
            actual_skill=actual_skill,
            expected_activation=expected_activation,
            actual_activation=actual_activation,
            input_tokens=token_metrics.input_tokens if token_metrics else None,
            output_tokens=token_metrics.output_tokens if token_metrics else None,
            total_tokens=token_metrics.total_tokens if token_metrics else None,
            token_source=token_metrics.source if token_metrics else None,
        ))

    # ---- 综合报告 ----

    def report(self) -> dict[str, Any]:
        """输出量化报告。"""
        result: dict[str, Any] = {}

        # 执行指标
        if self.records:
            total = len(self.records)
            success_count = sum(1 for r in self.records if r.success)
            tokens = [r.total_tokens for r in self.records]
            latencies = [r.latency_ms for r in self.records]
            sorted_lat = sorted(latencies)
            by_skill: dict[str, list[RuntimeMetrics]] = {}
            by_adapter: dict[str, list[RuntimeMetrics]] = {}
            for r in self.records:
                by_skill.setdefault(r.skill_name, []).append(r)
                by_adapter.setdefault(r.adapter_name, []).append(r)

            result["total_executions"] = total
            result["success_count"] = success_count
            result["success_rate"] = round(success_count / total, 4) if total else 0
            result["token_consumption"] = {
                "min": min(tokens),
                "max": max(tokens),
                "avg": round(sum(tokens) / len(tokens), 1),
                "total": sum(tokens),
            }
            result["token_source_counts"] = {
                source: sum(1 for r in self.records if r.token_source == source)
                for source in sorted({r.token_source for r in self.records})
            }
            result["latency_ms"] = {
                "min": round(min(latencies), 2),
                "max": round(max(latencies), 2),
                "avg": round(sum(latencies) / len(latencies), 2),
                "p50": round(sorted_lat[len(sorted_lat) // 2], 2),
                "p95": round(sorted_lat[int(len(sorted_lat) * 0.95)], 2) if len(sorted_lat) >= 20 else None,
            }
            result["by_skill"] = {
                name: {
                    "count": len(recs),
                    "avg_tokens": round(sum(r.total_tokens for r in recs) / len(recs), 1),
                    "avg_latency_ms": round(sum(r.latency_ms for r in recs) / len(recs), 2),
                    "success_rate": round(sum(1 for r in recs if r.success) / len(recs), 4),
                }
                for name, recs in sorted(by_skill.items())
            }
            result["by_adapter"] = {
                name: {
                    "count": len(recs),
                    "avg_tokens": round(sum(r.total_tokens for r in recs) / len(recs), 1),
                    "avg_latency_ms": round(sum(r.latency_ms for r in recs) / len(recs), 2),
                    "success_rate": round(sum(1 for r in recs if r.success) / len(recs), 4),
                }
                for name, recs in sorted(by_adapter.items())
            }

        # 混淆矩阵
        if self.eval_records:
            tp = tn = fp = fn = 0
            confidences: list[float] = []
            for rec in self.eval_records:
                if rec.expected_activation and rec.actual_activation:
                    if rec.expected_skill == rec.actual_skill:
                        tp += 1
                    else:
                        fp += 1
                elif not rec.expected_activation and not rec.actual_activation:
                    tn += 1
                elif rec.expected_activation and not rec.actual_activation:
                    fn += 1
                else:
                    fp += 1

            total_eval = tp + tn + fp + fn
            result["routing_eval_scope"] = {
                "source": "pytest_runtime_collector",
                "sample_count": total_eval,
                "description": "仅统计 pytest 运行过程中通过 RuntimeCollector 显式记录的路由样本；不等同于大样本 routing-eval-report。",
            }
            result["confusion_matrix"] = {"TP": tp, "TN": tn, "FP": fp, "FN": fn}
            result["activation_accuracy"] = safe_rate(tp + tn, total_eval)
            result["precision"] = safe_rate(tp, tp + fp)
            result["recall"] = safe_rate(tp, tp + fn)
            result["eval_details"] = [
                {
                    "query": rec.query[:80],
                    "expected_skill": rec.expected_skill,
                    "actual_skill": rec.actual_skill,
                    "expected_activation": rec.expected_activation,
                    "actual_activation": rec.actual_activation,
                    "total_tokens": rec.total_tokens,
                    "token_source": rec.token_source,
                }
                for rec in self.eval_records
            ]
            route_token_records = [rec for rec in self.eval_records if rec.total_tokens is not None]
            if route_token_records:
                route_tokens = [int(rec.total_tokens) for rec in route_token_records if rec.total_tokens is not None]
                result["routing_token_consumption"] = {
                    "min": min(route_tokens),
                    "max": max(route_tokens),
                    "avg": round(sum(route_tokens) / len(route_tokens), 1),
                    "total": sum(route_tokens),
                }
                result["routing_token_source_counts"] = {
                    source: sum(1 for rec in route_token_records if rec.token_source == source)
                    for source in sorted({rec.token_source for rec in route_token_records if rec.token_source})
                }

        return result

    def write_report(self, output_dir: str | Path) -> tuple[Path, Path]:
        """输出 JSON + Markdown 量化报告。"""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        report = self.report()

        json_path = out / "quantitative-report.json"
        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        md_path = out / "quantitative-report.md"
        md = _format_markdown(report, self.records, self.eval_records)
        md_path.write_text(md, encoding="utf-8")

        return json_path, md_path


def _format_markdown(report: dict, records: list[RuntimeMetrics], eval_records: list[EvalRecord]) -> str:
    if not report or "error" in report:
        return f"# 量化报告\n\n{report.get('error', '无数据')}\n"

    lines = [
        "# Skill Pipeline pytest 运行时量化报告",
        "",
        "> 本报告只统计 pytest 运行过程中 RuntimeCollector 显式记录的样本；路由混淆矩阵通常是小规模集成样本，不等同于 `routing-eval-report.*` 的大样本评测。",
        "",
    ]

    # ---- 路由准确度（混淆矩阵） ----
    cm = report.get("confusion_matrix")
    if cm:
        scope = report.get("routing_eval_scope", {})
        lines.extend([
            "## pytest 路由准确度（混淆矩阵）",
            "",
            f"- 样本来源: {scope.get('source', 'pytest_runtime_collector')}",
            f"- 样本数量: {scope.get('sample_count', sum(cm.values()))}",
            "- 大样本路由评测请查看 `routing-eval-report.md`。",
            "",
            f"| 指标 | 值 |",
            f"|------|-----|",
            f"| TP | {cm['TP']} |",
            f"| TN | {cm['TN']} |",
            f"| FP | {cm['FP']} |",
            f"| FN | {cm['FN']} |",
            f"| Accuracy | {report.get('activation_accuracy', 0):.1%} |",
            f"| Precision | {report.get('precision', 0):.1%} |",
            f"| Recall | {report.get('recall', 0):.1%} |",
            "",
        ])

        if report.get("eval_details"):
            lines.extend([
                "## 路由评测明细",
                "",
                "| # | Query | Expected | Actual | 预期激活 | 实际激活 |",
                "|---|-------|----------|--------|---------|---------|",
            ])
            for i, d in enumerate(report["eval_details"], 1):
                exp = "✅" if d["expected_activation"] else "❌"
                act = "✅" if d["actual_activation"] else "❌"
                lines.append(f"| {i} | {d['query']} | {d['expected_skill'] or '-'} | {d['actual_skill'] or '-'} | {exp} | {act} |")
            lines.append("")

        rtc = report.get("routing_token_consumption")
        if rtc:
            lines.extend([
                "## 路由 Token 消耗",
                "",
                "| 指标 | 值 |",
                "|------|-----|",
                f"| 单次最小 | {rtc['min']} |",
                f"| 单次最大 | {rtc['max']} |",
                f"| 单次平均 | {rtc['avg']} |",
                f"| 累计总消耗 | {rtc['total']} |",
                "",
            ])
        route_source_counts = report.get("routing_token_source_counts")
        if route_source_counts:
            lines.extend([
                "## 路由 Token 来源",
                "| 来源 | 次数 |",
                "|------|------|",
            ])
            for source, count in route_source_counts.items():
                lines.append(f"| {source} | {count} |")
            lines.append("")

    # ---- 执行概览 ----
    if "total_executions" in report:
        lines.extend([
            "## 执行概览",
            f"- 总执行次数: {report['total_executions']}",
            f"- 成功次数: {report['success_count']}",
            f"- 成功率: {report['success_rate']:.1%}",
            "",
        ])

    # ---- Token ----
    tc = report.get("token_consumption")
    if tc:
        lines.extend([
            "## Token 消耗",
            f"| 指标 | 值 |",
            f"|------|-----|",
            f"| 单次最小 | {tc['min']} |",
            f"| 单次最大 | {tc['max']} |",
            f"| 单次平均 | {tc['avg']} |",
            f"| 累计总消耗 | {tc['total']} |",
            "",
        ])
    source_counts = report.get("token_source_counts")
    if source_counts:
        lines.extend([
            "## Token 来源",
            "| 来源 | 次数 |",
            "|------|------|",
        ])
        for source, count in source_counts.items():
            lines.append(f"| {source} | {count} |")
        lines.append("")

    # ---- 延迟 ----
    lat = report.get("latency_ms")
    if lat:
        lines.extend([
            "## 延迟",
            f"| 指标 | 值 |",
            f"|------|-----|",
            f"| min | {lat['min']} ms |",
            f"| max | {lat['max']} ms |",
            f"| avg | {lat['avg']} ms |",
            f"| p50 | {lat['p50']} ms |",
        ])
        if lat.get("p95") is not None:
            lines.append(f"| p95 | {lat['p95']} ms |")
        lines.append("")

    # ---- 按 Skill 分组 ----
    bs = report.get("by_skill")
    if bs:
        lines.extend([
            "## 按 Skill 分组",
            "| Skill | 执行次数 | 平均 Token | 平均延迟 | 成功率 |",
            "|------|---------|-----------|---------|--------|",
        ])
        for name, info in bs.items():
            lines.append(f"| {name} | {info['count']} | {info['avg_tokens']} | {info['avg_latency_ms']}ms | {info['success_rate']:.1%} |")
        lines.append("")

    # ---- 按适配器分组 ----
    ba = report.get("by_adapter")
    if ba:
        lines.extend([
            "## 按适配器分组",
            "| 适配器 | 执行次数 | 平均 Token | 平均延迟 | 成功率 |",
            "|--------|---------|-----------|---------|--------|",
        ])
        for name, info in ba.items():
            lines.append(f"| {name} | {info['count']} | {info['avg_tokens']} | {info['avg_latency_ms']}ms | {info['success_rate']:.1%} |")
        lines.append("")

    # ---- 逐次明细 ----
    if records:
        lines.extend([
            "## 逐次执行明细",
            "| # | Skill | Adapter | Token | 延迟 | 结果 |",
            "|---|-------|---------|-------|------|------|",
        ])
        for i, r in enumerate(records, 1):
            status = "✅" if r.success else "❌"
            lines.append(f"| {i} | {r.skill_name} | {r.adapter_name} | {r.total_tokens} | {r.latency_ms:.2f}ms | {status} |")

    return "\n".join(lines) + "\n"
