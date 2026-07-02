"""Skill 路由与执行链路批量评测。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import json

from _skill.metrics import MetricsCollector
from _skill.models import MatchResult, NoSkillMatched, RedLineViolation, SkillAdapter, SkillIndex
from llm.skill_router import OpenAIChatSkillRouter


@dataclass(frozen=True)
class SkillEvalCase:
    """一条自然语言 skill 评测用例。"""

    name: str
    query: str
    expected_skill: str | None
    expected_activation: bool
    fields: dict[str, Any] | None = None
    should_block: bool = False
    expected_reason: str | None = None


@dataclass(frozen=True)
class SkillEvalCaseResult:
    """单条评测结果。"""

    name: str
    query: str
    expected_skill: str | None
    actual_skill: str | None
    expected_activation: bool
    executed: bool
    blocked: bool
    passed: bool
    reason: str


@dataclass(frozen=True)
class SkillEvalReport:
    """批量评测报告。"""

    summary: dict[str, Any]
    cases: list[SkillEvalCaseResult]


class SkillEvaluator:
    """运行自然语言到 skill 调用的批量评测，并输出报告。"""

    def __init__(self, index: SkillIndex, router: OpenAIChatSkillRouter, adapter: SkillAdapter) -> None:
        self.index = index
        self.router = router
        self.adapter = adapter

    def run(self, cases: list[SkillEvalCase]) -> SkillEvalReport:
        """运行一组评测用例。"""
        collector = MetricsCollector()
        results: list[SkillEvalCaseResult] = []

        for case in cases:
            call_result = self.router.route_and_execute(case.query, adapter=self.adapter, fields=case.fields)
            actual_skill = None
            blocked = isinstance(call_result.activation, RedLineViolation)
            executed = call_result.execution is not None

            if isinstance(call_result.activation, (MatchResult, RedLineViolation)):
                actual_skill = call_result.activation.skill.name

            activation_for_metrics = call_result.activation or NoSkillMatched()
            collector.record_activation(
                activation_for_metrics,
                expected_skill=case.expected_skill,
                expected_activation=case.expected_activation,
            )
            collector.record_redline(
                activation_for_metrics,
                should_block=case.should_block,
                expected_reason=case.expected_reason,
            )
            if call_result.execution is not None:
                collector.record_execution(call_result.execution)

            passed = (
                actual_skill == case.expected_skill
                and executed == case.expected_activation
                and blocked == case.should_block
            )
            if case.expected_skill is None:
                passed = actual_skill is None and not executed

            results.append(
                SkillEvalCaseResult(
                    name=case.name,
                    query=case.query,
                    expected_skill=case.expected_skill,
                    actual_skill=actual_skill,
                    expected_activation=case.expected_activation,
                    executed=executed,
                    blocked=blocked,
                    passed=passed,
                    reason=call_result.decision.reason,
                )
            )

        return SkillEvalReport(summary=collector.report(), cases=results)

    def write_report(self, report: SkillEvalReport, output_dir: str | Path) -> tuple[Path, Path]:
        """把评测报告写成 JSON 和 Markdown。"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        json_path = output_path / "skill_eval_report.json"
        md_path = output_path / "skill_eval_report.md"

        json_path.write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text(_format_markdown_report(report), encoding="utf-8")
        return json_path, md_path


def _format_markdown_report(report: SkillEvalReport) -> str:
    """生成 Markdown 评测报告。"""
    lines = ["# Skill Eval Report", "", "## Summary", ""]
    for key, value in report.summary.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Cases", "", "| Case | Expected | Actual | Executed | Blocked | Passed |", "|---|---|---|---|---|---|"])
    for case in report.cases:
        lines.append(
            f"| {case.name} | {case.expected_skill} | {case.actual_skill} | "
            f"{case.executed} | {case.blocked} | {case.passed} |"
        )
    return "\n".join(lines) + "\n"
