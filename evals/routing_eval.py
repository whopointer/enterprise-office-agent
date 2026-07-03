"""Skill 路由评测集加载与统计。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
import json
import time

from core.runtime_metrics import RuntimeCollector


@dataclass(frozen=True)
class RoutingEvalCase:
    """一条路由评测样本。"""

    case_id: str
    query: str
    expected_skill: str | None
    expected_activation: bool
    category: str
    difficulty: str
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class RoutingEvalResult:
    """一条路由评测结果。"""

    case: RoutingEvalCase
    actual_skill: str | None
    actual_activation: bool
    confidence: float | None
    latency_ms: float
    passed: bool
    reason: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    token_source: str | None = None


class SkillRouter(Protocol):
    """路由器最小协议。"""

    def route(self, user_query: str) -> Any:
        """返回包含 should_call / skill_name / confidence / reason 的对象。"""


def load_routing_eval_cases(path: str | Path) -> list[RoutingEvalCase]:
    """读取 JSONL 路由评测集。"""
    cases: list[RoutingEvalCase] = []
    for line_number, raw_line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        data = json.loads(line)
        try:
            cases.append(
                RoutingEvalCase(
                    case_id=str(data["id"]),
                    query=str(data["query"]),
                    expected_skill=data.get("expected_skill"),
                    expected_activation=bool(data["expected_activation"]),
                    category=str(data["category"]),
                    difficulty=str(data["difficulty"]),
                    tags=tuple(str(tag) for tag in data.get("tags", ())),
                )
            )
        except KeyError as exc:
            raise ValueError(f"{path}:{line_number} 缺少字段: {exc}") from exc
    return cases


def run_routing_eval(router: SkillRouter, cases: list[RoutingEvalCase]) -> tuple[list[RoutingEvalResult], dict[str, Any]]:
    """执行路由评测并返回结果与统计报告。"""
    results: list[RoutingEvalResult] = []
    collector = RuntimeCollector()

    for case in cases:
        start = time.perf_counter()
        decision = router.route(case.query)
        latency_ms = (time.perf_counter() - start) * 1000
        token_metrics = _last_token_metrics(router)
        actual_activation = bool(decision.should_call)
        actual_skill = decision.skill_name
        passed = (
            case.expected_activation == actual_activation
            and (not case.expected_activation or case.expected_skill == actual_skill)
        )
        confidence = getattr(decision, "confidence", None)
        reason = str(getattr(decision, "reason", ""))
        collector.record_routing(
            query=case.query,
            expected_skill=case.expected_skill,
            actual_skill=actual_skill,
            expected_activation=case.expected_activation,
            actual_activation=actual_activation,
            token_metrics=token_metrics,
        )
        results.append(
            RoutingEvalResult(
                case=case,
                actual_skill=actual_skill,
                actual_activation=actual_activation,
                confidence=confidence,
                latency_ms=latency_ms,
                passed=passed,
                reason=reason,
                input_tokens=token_metrics.input_tokens if token_metrics else None,
                output_tokens=token_metrics.output_tokens if token_metrics else None,
                total_tokens=token_metrics.total_tokens if token_metrics else None,
                token_source=token_metrics.source if token_metrics else None,
            )
        )

    report = collector.report()
    report["total_cases"] = len(results)
    report["passed_cases"] = sum(1 for result in results if result.passed)
    report["case_accuracy"] = _safe_rate(report["passed_cases"], report["total_cases"])
    report["by_category"] = _group_accuracy(results, lambda result: result.case.category)
    report["by_difficulty"] = _group_accuracy(results, lambda result: result.case.difficulty)
    report["confused_skill_pairs"] = _confused_skill_pairs(results)
    report["avg_latency_ms"] = round(sum(result.latency_ms for result in results) / len(results), 2) if results else 0
    report["avg_confidence_correct"] = _avg_confidence(result for result in results if result.passed)
    report["avg_confidence_wrong"] = _avg_confidence(result for result in results if not result.passed)
    report["failed_cases"] = [
        {
            "id": result.case.case_id,
            "query": result.case.query,
            "expected_skill": result.case.expected_skill,
            "actual_skill": result.actual_skill,
            "expected_activation": result.case.expected_activation,
            "actual_activation": result.actual_activation,
            "category": result.case.category,
            "difficulty": result.case.difficulty,
        }
        for result in results
        if not result.passed
    ]
    return results, report


def write_routing_eval_report(results: list[RoutingEvalResult], report: dict[str, Any], output_dir: str | Path) -> tuple[Path, Path]:
    """落盘 JSON + Markdown 路由评测报告。"""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "routing-eval-report.json"
    md_path = out / "routing-eval-report.md"
    payload = {
        "summary": report,
        "cases": [
            {
                "id": result.case.case_id,
                "query": result.case.query,
                "expected_skill": result.case.expected_skill,
                "actual_skill": result.actual_skill,
                "expected_activation": result.case.expected_activation,
                "actual_activation": result.actual_activation,
                "category": result.case.category,
                "difficulty": result.case.difficulty,
                "confidence": result.confidence,
                "latency_ms": round(result.latency_ms, 2),
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "total_tokens": result.total_tokens,
                "token_source": result.token_source,
                "passed": result.passed,
            }
            for result in results
        ],
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_format_markdown(report), encoding="utf-8")
    return json_path, md_path


def _group_accuracy(results: list[RoutingEvalResult], key_fn) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[RoutingEvalResult]] = {}
    for result in results:
        grouped.setdefault(key_fn(result), []).append(result)
    return {
        key: {
            "count": len(values),
            "passed": sum(1 for value in values if value.passed),
            "accuracy": _safe_rate(sum(1 for value in values if value.passed), len(values)),
        }
        for key, values in sorted(grouped.items())
    }


def _confused_skill_pairs(results: list[RoutingEvalResult]) -> dict[str, int]:
    pairs: dict[str, int] = {}
    for result in results:
        if result.passed:
            continue
        key = f"{result.case.expected_skill or '-'} -> {result.actual_skill or '-'}"
        pairs[key] = pairs.get(key, 0) + 1
    return dict(sorted(pairs.items(), key=lambda item: (-item[1], item[0])))


def _avg_confidence(results) -> float | None:
    values = [result.confidence for result in results if result.confidence is not None]
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _last_token_metrics(router: SkillRouter) -> Any:
    """读取路由器最近一次调用的 token 指标；不支持时返回 None。"""
    getter = getattr(router, "last_token_metrics", None)
    if not callable(getter):
        return None
    return getter()


def _safe_rate(numerator: int | float, denominator: int | float) -> float:
    if denominator == 0:
        return 1.0
    return round(float(numerator) / float(denominator), 4)


def _format_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Skill 路由评测报告",
        "",
        f"- 总样本数: {report.get('total_cases', 0)}",
        f"- 通过样本数: {report.get('passed_cases', 0)}",
        f"- Case Accuracy: {report.get('case_accuracy', 0):.1%}",
    ]
    cm = report.get("confusion_matrix")
    if cm:
        lines.extend([
            f"- TP: {cm['TP']}",
            f"- TN: {cm['TN']}",
            f"- FP: {cm['FP']}",
            f"- FN: {cm['FN']}",
            f"- Precision: {report.get('precision', 0):.1%}",
            f"- Recall: {report.get('recall', 0):.1%}",
        ])
    route_tokens = report.get("routing_token_consumption")
    if route_tokens:
        lines.extend([
            f"- 路由 Token 总消耗: {route_tokens['total']}",
            f"- 路由 Token 单次平均: {route_tokens['avg']}",
        ])
    source_counts = report.get("routing_token_source_counts")
    if source_counts:
        source_text = ", ".join(f"{source}: {count}" for source, count in source_counts.items())
        lines.append(f"- 路由 Token 来源: {source_text}")
    lines.extend(["", "## 按类别", "", "| Category | Count | Passed | Accuracy |", "|---|---:|---:|---:|"])
    for category, info in report.get("by_category", {}).items():
        lines.append(f"| {category} | {info['count']} | {info['passed']} | {info['accuracy']:.1%} |")
    lines.extend(["", "## 按难度", "", "| Difficulty | Count | Passed | Accuracy |", "|---|---:|---:|---:|"])
    for difficulty, info in report.get("by_difficulty", {}).items():
        lines.append(f"| {difficulty} | {info['count']} | {info['passed']} | {info['accuracy']:.1%} |")
    if report.get("confused_skill_pairs"):
        lines.extend(["", "## 混淆对", "", "| Pair | Count |", "|---|---:|"])
        for pair, count in report["confused_skill_pairs"].items():
            lines.append(f"| {pair} | {count} |")
    return "\n".join(lines) + "\n"
