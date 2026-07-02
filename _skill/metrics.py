"""综合量化指标采集。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import ExecutionResult, MatchResult, NoSkillMatched, RedLineViolation
from .utils import average, safe_rate


class MetricsCollector:
    """跨用例量化统计器，用于输出 design.md 要求的综合指标。"""

    def __init__(self) -> None:
        self.tp = 0
        self.tn = 0
        self.fp = 0
        self.fn = 0
        self.confidences: list[float] = []
        self.redline_should_block = 0
        self.redline_blocked = 0
        self.redline_should_pass = 0
        self.redline_passed = 0
        self.redline_false_block = 0
        self.redline_reason_matched = 0
        self.redline_reason_total = 0
        self.execution_total = 0
        self.execution_success = 0
        self.adapter_success: dict[str, list[bool]] = {}
        self.adapter_latency: dict[str, list[float]] = {}
        self.artifact_total = 0
        self.artifact_success = 0

    def record_activation(
        self,
        result: MatchResult | NoSkillMatched | RedLineViolation,
        *,
        expected_skill: str | None,
        expected_activation: bool,
    ) -> None:
        """记录 skill 激活准确率相关指标。"""
        if isinstance(result, MatchResult):
            actual_skill = result.skill.name
            if expected_activation and actual_skill == expected_skill:
                self.tp += 1
                self.confidences.append(result.confidence)
            else:
                self.fp += 1
            return

        if expected_activation:
            self.fn += 1
        else:
            self.tn += 1

    def record_redline(
        self,
        result: MatchResult | NoSkillMatched | RedLineViolation,
        *,
        should_block: bool,
        expected_reason: str | None = None,
    ) -> None:
        """记录红线拦截质量指标。"""
        blocked = isinstance(result, RedLineViolation)
        if should_block:
            self.redline_should_block += 1
            if blocked:
                self.redline_blocked += 1
        else:
            self.redline_should_pass += 1
            if not blocked:
                self.redline_passed += 1
            else:
                self.redline_false_block += 1

        if expected_reason is not None:
            self.redline_reason_total += 1
            actual_reason = result.reason if hasattr(result, "reason") else ""
            if expected_reason in actual_reason:
                self.redline_reason_matched += 1

    def record_execution(self, result: ExecutionResult) -> None:
        """记录执行成功率、适配器成功率、耗时和产物指标。"""
        self.execution_total += 1
        if result.metrics.execution_success:
            self.execution_success += 1

        adapter_name = result.metrics.adapter_name
        self.adapter_success.setdefault(adapter_name, []).append(result.metrics.execution_success)
        self.adapter_latency.setdefault(adapter_name, []).append(result.metrics.latency_ms)

        if result.asset_paths:
            self.artifact_total += len(result.asset_paths)
            self.artifact_success += sum(1 for path in result.asset_paths if Path(path).exists())

    def report(self) -> dict[str, Any]:
        """输出综合量化报告。"""
        total_activation = self.tp + self.tn + self.fp + self.fn
        return {
            "activation_accuracy": safe_rate(self.tp + self.tn, total_activation),
            "precision": safe_rate(self.tp, self.tp + self.fp),
            "recall": safe_rate(self.tp, self.tp + self.fn),
            "false_positive_rate": safe_rate(self.fp, self.fp + self.tn),
            "false_negative_rate": safe_rate(self.fn, self.fn + self.tp),
            "confidence_avg": average(self.confidences),
            "confusion_matrix": {"TP": self.tp, "TN": self.tn, "FP": self.fp, "FN": self.fn},
            "redline_block_rate": safe_rate(self.redline_blocked, self.redline_should_block),
            "redline_pass_rate": safe_rate(self.redline_passed, self.redline_should_pass),
            "redline_false_block_rate": safe_rate(self.redline_false_block, self.redline_should_pass),
            "redline_reason_match_rate": safe_rate(self.redline_reason_matched, self.redline_reason_total),
            "execution_success_rate": safe_rate(self.execution_success, self.execution_total),
            "adapter_success_rate": {
                name: safe_rate(sum(1 for ok in values if ok), len(values))
                for name, values in self.adapter_success.items()
            },
            "latency_ms_avg": {name: average(values) for name, values in self.adapter_latency.items()},
            "artifact_success_rate": safe_rate(self.artifact_success, self.artifact_total),
        }
