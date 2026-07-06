"""QA 质量评估器的本地确定性测试。"""

from __future__ import annotations

from pathlib import Path
import json

from evals.qa_quality import evaluate_answer_locally, normalize_case
from tests import test_skill_qa


REPO_ROOT = Path(__file__).resolve().parent.parent


def test_local_evaluator_accepts_ordered_technical_executable_answer() -> None:
    """答案满足顺序、技术断言、配置和文档标准时应通过。"""
    case = normalize_case({
        "id": "QA-X",
        "query": "生成 render.yaml",
        "expected_skill": "render-deploy",
        "must_include": ["render.yaml", "PORT"],
        "ordered_steps": ["前提", "配置", "部署", "验证"],
        "technical_checks": [
            {"id": "port", "must_include": ["PORT"], "must_not_include": ["固定 3000"]},
        ],
        "config_checks": [
            {"id": "render_yaml", "type": "render_yaml", "required": True, "required_service_fields": ["type", "name"]},
        ],
        "document_standard": {"min_sections": 3, "min_chars": 80, "required_sections_any": [["前提"], ["配置"], ["验证"]]},
        "quality_thresholds": {"local_score": 0.8, "components": {"forbidden": 1.0}},
    })
    output = """## 前提
代码已推送到 GitHub。

## 配置
下面是 render.yaml，服务通过 PORT 读取端口。

```yaml
services:
  - type: web
    name: api
    env: node
    startCommand: npm start
```

## 部署
在 Render Blueprint 中应用配置。

## 验证
查看日志和健康检查。
"""

    result = evaluate_answer_locally(output, case)

    assert result["pass"] is True
    assert result["components"]["ordered_steps"] == 1.0
    assert result["components"]["technical_checks"] == 1.0
    assert result["components"]["config_checks"] == 1.0
    assert result["components"]["document_standard"] == 1.0


def test_local_evaluator_rejects_hidden_critical_config_errors() -> None:
    """隐蔽严重错误、顺序错误和不可执行配置应被拦截。"""
    case = normalize_case({
        "id": "QA-BAD",
        "query": "部署 Express",
        "expected_skill": "render-deploy",
        "must_include": ["PORT", "startCommand"],
        "forbidden": ["固定 3000 端口即可"],
        "ordered_steps": ["前提", "配置", "部署"],
        "technical_checks": [
            {"id": "port", "must_include": ["PORT"], "must_not_include": ["固定 3000"]},
        ],
        "config_checks": [
            {"id": "render_yaml", "type": "render_yaml", "required": True, "required_service_fields": ["type", "name"]},
        ],
        "document_standard": {"min_sections": 3, "min_chars": 80},
        "quality_thresholds": {"local_score": 0.8, "components": {"forbidden": 1.0}},
    })
    output = """直接部署即可，固定 3000 端口即可。

```yaml
foo: bar
```
"""

    result = evaluate_answer_locally(output, case)

    assert result["pass"] is False
    assert result["forbidden"]["violations"]
    assert result["technical_checks"]["failed"] == ["port"]
    assert result["config_checks"]["failed"]
    assert result["document_standard"]["issues"]


def test_normalize_case_keeps_legacy_expected_elements() -> None:
    """旧数据集的 expected_elements 应映射为 must_include。"""
    case = normalize_case({"id": "old", "query": "q", "expected_elements": ["A", "B"]})

    assert case["turns"] == ["q"]
    assert case["must_include"] == ["A", "B"]


def test_render_deploy_qa_dataset_contains_strict_quality_dimensions() -> None:
    """真实 QA 数据集必须覆盖严格答案质量维度。"""
    cases = json.loads((REPO_ROOT / "datasets" / "render-deploy-qa.json").read_text(encoding="utf-8"))
    positive_cases = [case for case in cases if case.get("expected_skill")]

    assert len(cases) == 20
    assert positive_cases
    for case in positive_cases:
        assert case.get("must_include"), case["id"]
        assert case.get("ordered_steps"), case["id"]
        assert case.get("technical_checks"), case["id"]
        assert case.get("document_standard", {}).get("required_sections_any"), case["id"]
        rubric = case.get("judge_rubric", {})
        for key in [
            "technical_correctness",
            "step_order",
            "config_executability",
            "problem_resolution",
            "hidden_critical_errors",
            "document_standard",
        ]:
            assert rubric.get(key), f"{case['id']} missing {key}"
        thresholds = case.get("quality_thresholds", {})
        assert thresholds.get("local_score", 0) >= 0.65
        assert thresholds.get("judge_score", 0) >= 0.70


def test_judge_result_rejects_critical_issues_even_with_high_score() -> None:
    """LLM judge 发现严重问题时，即使 overall 高也不能通过。"""
    result = test_skill_qa._normalize_judge_result({
        "technical_correctness": 0.9,
        "step_order": 0.9,
        "config_executability": 0.9,
        "problem_resolution": 0.9,
        "hidden_critical_errors": 0.2,
        "document_standard": 0.9,
        "overall": 0.92,
        "critical_issues": ["忽略 PORT，固定端口会导致 Render 部署失败"],
        "_threshold": 0.7,
    })

    assert result["pass"] is False
    assert result["critical_issues"]


def test_judge_result_demotes_non_critical_issues_to_warnings() -> None:
    """judge 把普通风险写进 critical_issues 时，应按严重错误分数降级。"""
    result = test_skill_qa._normalize_judge_result({
        "technical_correctness": 0.9,
        "step_order": 0.9,
        "config_executability": 0.85,
        "problem_resolution": 0.9,
        "hidden_critical_errors": 1.0,
        "document_standard": 0.85,
        "overall": 0.9,
        "critical_issues": ["配置示例可补充更多字段"],
        "_threshold": 0.7,
        "_critical_threshold": 0.8,
    })

    assert result["pass"] is True
    assert result["critical_issues"] == []
    assert result["warnings"] == ["配置示例可补充更多字段"]


def test_unavailable_case_is_recorded_for_summary_report() -> None:
    """LLM 异常或 skip 也应进入 QA 报告，避免总量口径缺失。"""
    original = list(test_skill_qa._qa_results)
    test_skill_qa._qa_results.clear()
    try:
        test_skill_qa._record_unavailable_case(
            {
                "id": "QA-SKIP",
                "expected_skill": "render-deploy",
                "must_include": ["PORT"],
            },
            stage="route_invalid",
            reason="LLM 返回异常",
            routing_tokens=123,
        )

        result = test_skill_qa._qa_results[0]
        assert result["id"] == "QA-SKIP"
        assert result["status"] == "route_invalid_skipped"
        assert result["failure_reasons"] == ["route_invalid"]
        assert result["must_total"] == 1
        assert result["critical_issues"] == ["LLM 返回异常"]
    finally:
        test_skill_qa._qa_results[:] = original
