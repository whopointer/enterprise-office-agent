"""大样本路由评测集与统计 runner 测试。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from evals.routing_eval import (
    load_routing_eval_cases,
    run_routing_eval,
    write_routing_eval_report,
)


@dataclass(frozen=True)
class _Decision:
    should_call: bool
    skill_name: str | None
    confidence: float
    reason: str = "fake"


class _OracleRouter:
    """按评测集期望返回结果，用于测试 runner 统计逻辑。"""

    def __init__(self, cases):
        self._by_query = {case.query: case for case in cases}

    def route(self, user_query: str) -> _Decision:
        case = self._by_query[user_query]
        return _Decision(
            should_call=case.expected_activation,
            skill_name=case.expected_skill,
            confidence=0.95,
        )


def _dataset_path() -> Path:
    return Path(__file__).resolve().parents[1] / "datasets" / "skill_routing_eval.jsonl"


def test_routing_eval_dataset_has_target_size_and_distribution() -> None:
    """路由评测集应达到第一阶段 100-120 条规模，并覆盖关键类别。"""
    cases = load_routing_eval_cases(_dataset_path())
    by_category: dict[str, int] = {}
    by_difficulty: dict[str, int] = {}
    for case in cases:
        by_category[case.category] = by_category.get(case.category, 0) + 1
        by_difficulty[case.difficulty] = by_difficulty.get(case.difficulty, 0) + 1

    assert len(cases) == 120
    assert by_category["document_generation"] == 15
    assert by_category["deployment"] == 15
    assert by_category["other_skill"] == 20
    assert by_category["irrelevant"] == 20
    assert by_category["ambiguous"] == 20
    assert by_category["confusing_negative"] == 20
    assert by_category["field_noise"] == 10
    assert by_difficulty["hard"] >= 40
    assert by_difficulty["medium"] >= 30
    assert by_difficulty["easy"] >= 40


def test_routing_eval_dataset_uses_valid_skill_names() -> None:
    """expected_skill 必须使用 SKILL.md 里的 name，而不是目录名。"""
    cases = load_routing_eval_cases(_dataset_path())
    expected_skills = {case.expected_skill for case in cases if case.expected_skill}

    assert "docx-report-generator" in expected_skills
    assert "render-deploy" in expected_skills
    assert "word-report-generator-1.0.0" not in expected_skills


def test_routing_eval_runner_reports_large_confusion_matrix(tmp_path: Path) -> None:
    """runner 应能对 120 条样本输出混淆矩阵和分组准确率。"""
    cases = load_routing_eval_cases(_dataset_path())
    results, report = run_routing_eval(_OracleRouter(cases), cases)
    json_path, md_path = write_routing_eval_report(results, report, tmp_path)

    assert report["total_cases"] == 120
    assert report["passed_cases"] == 120
    assert report["case_accuracy"] == 1.0
    assert report["confusion_matrix"] == {"TP": 80, "TN": 40, "FP": 0, "FN": 0}
    assert report["by_category"]["ambiguous"]["count"] == 20
    assert report["by_difficulty"]["hard"]["count"] == 40
    assert json_path.exists()
    assert md_path.exists()
    assert "Skill 路由评测报告" in md_path.read_text(encoding="utf-8")
