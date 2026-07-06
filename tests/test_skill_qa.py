"""Render Deploy 问答集自动化测试 — 评估 LLM 输出质量。

从 datasets/render-deploy-qa.json 读取 20 条用例，逐条调真实 LLM，
对比路由、确定性质量规则和 LLM-as-judge 语义评分，输出量化评分报告。
"""

from __future__ import annotations

from pathlib import Path
import json
import os

import pytest
from openai import APIStatusError, RateLimitError

from _skill import (
    FileSkillDiscovery,
)
from evals.llm_answer_runner import EvalLLMAnswerRunner
from evals.qa_quality import evaluate_answer_locally, normalize_case
from llm.skill_router import (
    LLMRouterResponseError,
    OpenAIChatSkillRouter,
    load_skill_env,
)
from llm.schema import LLMDecisionSchemaError

load_skill_env()

LLM_MARK = pytest.mark.skipif(
    not (os.environ.get("API_KEY") or os.environ.get("OPENAI_API_KEY")),
    reason="需要 API_KEY",
)

DS_PATH = Path(__file__).resolve().parent.parent / "datasets" / "render-deploy-qa.json"
REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_cases() -> list[dict]:
    with open(DS_PATH, encoding="utf-8") as f:
        return [normalize_case(case) for case in json.load(f)]


def _build_index():
    return FileSkillDiscovery(REPO_ROOT / "skills").discover()


def _chinese_ratio(text: str) -> float:
    """中文字符占比。"""
    if not text:
        return 0.0
    chinese = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    return chinese / len(text)


def _judge_answer_with_llm(case: dict, output: str) -> dict:
    """用真实 LLM 评估语义正确性和隐藏风险。"""
    rubric = case.get("judge_rubric", {})
    thresholds = case.get("quality_thresholds", {})
    prompt = {
        "task": "你是严格的软件工程评测员。请只输出 JSON object，不要 Markdown。",
        "user_query": case.get("query"),
        "expected_skill": case.get("expected_skill"),
        "case_description": case.get("description"),
        "rubric": rubric,
        "answer": output,
        "scoring": {
            "technical_correctness": "方案是否符合真实 Render/部署/文档生成技术规则，是否有明显错误。",
            "step_order": "步骤顺序是否合理，是否先满足前置条件，再配置，再部署，再验证。",
            "config_executability": "如果涉及配置，配置是否可执行、字段是否合理、是否避免伪造配置。",
            "problem_resolution": "是否直接解决用户具体问题，而不是泛泛解释。",
            "hidden_critical_errors": "是否存在隐蔽但严重的错误、误导性安全建议、错误命令或错误部署假设。",
            "document_standard": "如果用户要文档/产物，结构是否标准、章节是否完整、是否像可交付文档。",
        },
        "required_json_schema": {
            "technical_correctness": "number 0..1",
            "step_order": "number 0..1",
            "config_executability": "number 0..1",
            "problem_resolution": "number 0..1",
            "hidden_critical_errors": "number 0..1; 1 表示没有严重错误",
            "document_standard": "number 0..1",
            "overall": "number 0..1",
            "critical_issues": "array[string]; 只填写足以判定答案失败的严重错误",
            "warnings": "array[string]; 填写不一定导致失败的风险、缺失或改进项",
            "reason": "string",
        },
    }
    parsed = EvalLLMAnswerRunner().judge_json(prompt)
    parsed["_threshold"] = thresholds.get("judge_score", 0.70)
    parsed["_critical_threshold"] = thresholds.get("critical_error_score", 0.80)
    return _normalize_judge_result(parsed)


def _normalize_judge_result(data: dict) -> dict:
    """规整 judge 分数，避免异常类型影响报告。"""
    keys = [
        "technical_correctness",
        "step_order",
        "config_executability",
        "problem_resolution",
        "hidden_critical_errors",
        "document_standard",
        "overall",
    ]
    result = {}
    for key in keys:
        result[key] = _clamp_score(data.get(key, 0))
    issues = data.get("critical_issues", [])
    warnings = data.get("warnings", [])
    result["critical_issues"] = issues if isinstance(issues, list) else [str(issues)]
    result["warnings"] = warnings if isinstance(warnings, list) else [str(warnings)]

    # 有些 judge 会把普通风险误放进 critical_issues，但同时给出“无严重错误”的高分。
    # 这里以 hidden_critical_errors 作为严重性闸门，把非致命项降级为 warning。
    critical_threshold = float(data.get("_critical_threshold", 0.80))
    if result["critical_issues"] and result["hidden_critical_errors"] >= critical_threshold:
        result["warnings"].extend(result["critical_issues"])
        result["critical_issues"] = []

    result["reason"] = str(data.get("reason", ""))
    result["threshold"] = float(data.get("_threshold", 0.70))
    result["critical_threshold"] = critical_threshold
    result["pass"] = (
        result["overall"] >= result["threshold"]
        and result["hidden_critical_errors"] >= critical_threshold
        and not result["critical_issues"]
    )
    return result


def _clamp_score(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))


def _failure_reasons(case_result: dict, local_eval: dict, judge_eval: dict, cn_ratio: float) -> list[str]:
    """把失败原因归类，便于报告定位。"""
    reasons = []
    if not case_result["routing_correct"]:
        reasons.append("routing")
    if not local_eval["pass"]:
        reasons.append("local_quality")
    if not judge_eval["pass"]:
        reasons.append("judge_quality")
    if cn_ratio <= 0.10:
        reasons.append("language")
    if case_result["hallucination_count"] > 0:
        reasons.append("hallucination")
    if case_result.get("critical_issues"):
        reasons.append("critical_issue")
    return reasons


def _record_unavailable_case(case: dict, *, stage: str, reason: str, routing_tokens: int | None = None) -> None:
    """供应商或返回格式异常时也要进入报告，避免样本静默丢失。"""
    expected_skill = case.get("expected_skill")
    _qa_results.append({
        "id": case["id"],
        "status": f"{stage}_skipped",
        "expected_skill": expected_skill,
        "actual_skill": None,
        "routing_correct": False,
        "expected_activation": expected_skill is not None,
        "actual_activation": None,
        "local_score": 0.0 if expected_skill else None,
        "local_pass": False if expected_skill else None,
        "judge_score": 0.0 if expected_skill else None,
        "judge_pass": False if expected_skill else None,
        "judge_components": {},
        "must_hits": 0,
        "must_total": len(case.get("must_include", [])) if expected_skill else 0,
        "missed": case.get("must_include", []) if expected_skill else [],
        "forbidden_violations": [],
        "ordered_step_score": 0.0 if expected_skill else None,
        "config_score": 0.0 if expected_skill else None,
        "document_standard_score": 0.0 if expected_skill else None,
        "chinese_ratio": 0.0 if expected_skill else None,
        "hallucination_count": 0,
        "hallucinations": [],
        "critical_issues": [reason],
        "warnings": [],
        "judge_reason": reason,
        "answer_excerpt": "",
        "local_details": {},
        "tokens": 0,
        "routing_tokens": routing_tokens,
        "difficulty": case.get("difficulty", ""),
        "failure_reasons": [stage],
    })


# ---------------------------------------------------------------------------
# 逐条测试
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["id"])
@LLM_MARK
def test_qa_case(case, runtime_collector):
    """逐条运行问答对并评估。"""
    query = case["query"]
    expected_skill = case["expected_skill"]

    index = _build_index()

    # ── 路由 ──
    router = OpenAIChatSkillRouter(index)
    try:
        decision = router.route(query)
    except (RateLimitError, APIStatusError) as exc:
        status = getattr(exc, "status_code", 0)
        if status in {401, 403, 429, 503}:
            _record_unavailable_case(
                case,
                stage="route_unavailable",
                reason=f"供应商不可用({status})",
                routing_tokens=_token_total(router.last_token_metrics()),
            )
            pytest.skip(f"供应商不可用({status})")
        raise
    except (LLMRouterResponseError, LLMDecisionSchemaError) as exc:
        _record_unavailable_case(
            case,
            stage="route_invalid",
            reason=f"LLM 返回异常: {exc}",
            routing_tokens=_token_total(router.last_token_metrics()),
        )
        pytest.skip("LLM 返回异常")

    actual_skill = decision.skill_name
    routing_correct = actual_skill == expected_skill

    # ── 记录路由评估 ──
    runtime_collector.record_routing(
        query=case["id"],
        expected_skill=expected_skill,
        actual_skill=actual_skill,
        expected_activation=expected_skill is not None,
        actual_activation=decision.should_call,
        token_metrics=router.last_token_metrics(),
    )

    # ── 阴性对照：期望不激活 ──
    if expected_skill is None:
        _qa_results.append({
            "id": case["id"],
            "status": "negative_pass" if not decision.should_call else "negative_failed",
            "expected_skill": expected_skill,
            "actual_skill": actual_skill,
            "routing_correct": not decision.should_call,
            "expected_activation": False,
            "actual_activation": decision.should_call,
            "local_score": None,
            "local_pass": None,
            "judge_score": None,
            "judge_pass": None,
            "judge_components": {},
            "must_hits": 0,
            "must_total": 0,
            "missed": [],
            "forbidden_violations": [],
            "ordered_step_score": None,
            "config_score": None,
            "document_standard_score": None,
            "chinese_ratio": None,
            "hallucination_count": 0,
            "hallucinations": [],
            "critical_issues": [] if not decision.should_call else [f"负例被错误激活: {actual_skill}"],
            "warnings": [],
            "judge_reason": "",
            "tokens": 0,
            "routing_tokens": _token_total(router.last_token_metrics()),
            "difficulty": case.get("difficulty", ""),
            "failure_reasons": [] if not decision.should_call else ["negative_activation"],
        })
        assert not decision.should_call, f"{case['id']}: 期望不激活但 LLM 选中了 {actual_skill}"
        return

    # ── 执行 ──
    if not decision.should_call or actual_skill is None:
        # LLM 漏判（FN）—— 真实数据，记录 skip
        _qa_results.append({
            "id": case["id"],
            "status": "missed_activation",
            "expected_skill": expected_skill,
            "actual_skill": actual_skill,
            "routing_correct": False,
            "expected_activation": True,
            "actual_activation": decision.should_call,
            "local_score": 0.0,
            "local_pass": False,
            "judge_score": 0.0,
            "judge_pass": False,
            "judge_components": {},
            "must_hits": 0,
            "must_total": len(case.get("must_include", [])),
            "missed": case.get("must_include", []),
            "forbidden_violations": [],
            "ordered_step_score": 0.0,
            "config_score": 0.0,
            "document_standard_score": 0.0,
            "chinese_ratio": 0.0,
            "hallucination_count": 0,
            "hallucinations": [],
            "critical_issues": ["LLM 未激活"],
            "warnings": [],
            "judge_reason": "",
            "tokens": 0,
            "routing_tokens": _token_total(router.last_token_metrics()),
            "difficulty": case.get("difficulty", ""),
            "note": f"LLM 未激活 (FN)，expected={expected_skill}",
            "failure_reasons": ["missed_activation"],
        })
        return  # 不 fail，仅记录

    if not routing_correct:
        _qa_results.append({
            "id": case["id"],
            "status": "routing_failed",
            "expected_skill": expected_skill,
            "actual_skill": actual_skill,
            "routing_correct": False,
            "expected_activation": True,
            "actual_activation": decision.should_call,
            "local_score": 0.0,
            "local_pass": False,
            "judge_score": 0.0,
            "judge_pass": False,
            "judge_components": {},
            "must_hits": 0,
            "must_total": len(case.get("must_include", [])),
            "missed": case.get("must_include", []),
            "forbidden_violations": [],
            "ordered_step_score": 0.0,
            "config_score": 0.0,
            "document_standard_score": 0.0,
            "chinese_ratio": 0.0,
            "hallucination_count": 0,
            "hallucinations": [],
            "critical_issues": [f"路由错误: expected={expected_skill}, actual={actual_skill}"],
            "warnings": [],
            "judge_reason": "",
            "tokens": 0,
            "routing_tokens": _token_total(router.last_token_metrics()),
            "difficulty": case.get("difficulty", ""),
            "failure_reasons": ["routing"],
        })
        assert routing_correct, f"{case['id']}: 期望 {expected_skill} 实际 {actual_skill}"

    skill = index.get(actual_skill)
    runner = EvalLLMAnswerRunner()
    result = runner.run(skill, user_query=query, fields=decision.fields)

    runtime_collector.record(skill.name, result.metrics)

    output = str(result.output)

    # ── 本地确定性质量检查 ──
    local_eval = evaluate_answer_locally(output, case, skill_dir=skill.directory)

    # ── 语言一致性 ──
    cn_ratio = _chinese_ratio(output)

    # ── LLM-as-judge 语义质量检查 ──
    try:
        judge_eval = _judge_answer_with_llm(case, output)
    except (RateLimitError, APIStatusError) as exc:
        status = getattr(exc, "status_code", 0)
        if status in {401, 403, 429, 503}:
            _record_unavailable_case(
                case,
                stage="judge_unavailable",
                reason=f"judge 供应商不可用({status})",
                routing_tokens=routing_tokens,
            )
            pytest.skip(f"judge 供应商不可用({status})")
        raise

    # ── Token ──
    tokens = result.metrics.token_metrics.total_tokens
    routing_tokens = _token_total(router.last_token_metrics())
    hallucinations = local_eval["hallucination"]["hallucinations"]
    must = local_eval["must_include"]

    # 落盘单条结果
    case_result = {
        "id": case["id"],
        "status": "passed",
        "expected_skill": expected_skill,
        "actual_skill": actual_skill,
        "routing_correct": routing_correct,
        "expected_activation": True,
        "actual_activation": decision.should_call,
        "local_score": local_eval["score"],
        "local_pass": local_eval["pass"],
        "judge_score": judge_eval["overall"],
        "judge_pass": judge_eval["pass"],
        "judge_components": {k: judge_eval[k] for k in [
            "technical_correctness",
            "step_order",
            "config_executability",
            "problem_resolution",
            "hidden_critical_errors",
            "document_standard",
        ]},
        "must_hits": must["hits"],
        "must_total": must["total"],
        "missed": must["missed"],
        "forbidden_violations": local_eval["forbidden"]["violations"],
        "ordered_step_score": local_eval["components"]["ordered_steps"],
        "config_score": local_eval["components"]["config_checks"],
        "document_standard_score": local_eval["components"]["document_standard"],
        "chinese_ratio": round(cn_ratio, 2),
        "hallucination_count": len(hallucinations),
        "hallucinations": hallucinations,
        "critical_issues": judge_eval["critical_issues"],
        "warnings": judge_eval["warnings"],
        "judge_reason": judge_eval["reason"],
        "answer_excerpt": output[:1200],
        "local_details": local_eval,
        "tokens": tokens,
        "routing_tokens": routing_tokens,
        "difficulty": case.get("difficulty", ""),
    }
    case_result["failure_reasons"] = _failure_reasons(case_result, local_eval, judge_eval, cn_ratio)
    if case_result["failure_reasons"]:
        case_result["status"] = "failed"

    # 把结果存入 collector 用于汇总报告
    _qa_results.append(case_result)

    assert routing_correct, f"{case['id']}: 路由错误"
    assert local_eval["pass"], f"{case['id']}: 本地质量检查失败 {local_eval}"
    assert judge_eval["pass"], f"{case['id']}: judge 质量检查失败 {judge_eval}"
    assert cn_ratio > 0.10, f"{case['id']}: 中文比例过低 ({cn_ratio:.0%})"
    assert len(hallucinations) == 0, f"{case['id']}: 检测到幻觉引用 {hallucinations}"


# ---------------------------------------------------------------------------
# 汇总报告
# ---------------------------------------------------------------------------

_qa_results: list[dict] = []


def _token_total(metrics) -> int | None:
    """读取 token 总数；供应商没有 usage 时返回 None。"""
    return metrics.total_tokens if metrics else None


class TestQASummary:
    """汇总所有 QA 结果，输出量化评分报告。"""

    @LLM_MARK
    def test_qa_summary_report(self):
        """在所有 QA 用例跑完后生成汇总评分。"""
        if not _qa_results:
            pytest.skip("无 QA 结果（可能全部 skip）")

        total = len(_qa_results)
        positive_results = [r for r in _qa_results if r.get("expected_activation") is True]
        answered_results = [r for r in positive_results if r.get("tokens", 0) > 0]
        routing_correct = sum(1 for r in _qa_results if r["routing_correct"])
        total_elements = sum(r["must_total"] for r in positive_results)
        total_hits = sum(r["must_hits"] for r in positive_results)
        hallucination_cases = sum(1 for r in _qa_results if r["hallucination_count"] > 0)
        cn_scored = [r for r in answered_results if r.get("chinese_ratio") is not None]
        cn_ok = sum(1 for r in cn_scored if r["chinese_ratio"] > 0.10)
        local_scores = [r["local_score"] for r in positive_results if r.get("local_score") is not None]
        judge_scores = [r["judge_score"] for r in positive_results if r.get("judge_score") is not None]
        critical_issue_cases = sum(1 for r in _qa_results if r.get("critical_issues"))
        tokens = [r["tokens"] for r in answered_results]
        routing_tokens = [r["routing_tokens"] for r in _qa_results if r.get("routing_tokens") is not None]
        failed_cases = [r for r in _qa_results if r.get("failure_reasons")]
        failure_distribution = {}
        for result in failed_cases:
            for reason in result.get("failure_reasons", []):
                failure_distribution[reason] = failure_distribution.get(reason, 0) + 1

        report = {
            "total_cases": total,
            "positive_cases": len(positive_results),
            "answered_cases": len(answered_results),
            "failed_cases": len(failed_cases),
            "routing_accuracy": round(routing_correct / total, 4),
            "element_hit_rate": round(total_hits / total_elements, 4) if total_elements else 0,
            "local_quality_score": round(sum(local_scores) / len(local_scores), 4) if local_scores else 0,
            "judge_quality_score": round(sum(judge_scores) / len(judge_scores), 4) if judge_scores else 0,
            "language_consistency": round(cn_ok / len(cn_scored), 4) if cn_scored else 0,
            "hallucination_free_rate": round((total - hallucination_cases) / total, 4),
            "critical_error_free_rate": round((total - critical_issue_cases) / total, 4),
            "token_avg": round(sum(tokens) / len(tokens), 1) if tokens else 0,
            "token_total": sum(tokens),
            "routing_token_avg": round(sum(routing_tokens) / len(routing_tokens), 1) if routing_tokens else None,
            "routing_token_total": sum(routing_tokens) if routing_tokens else None,
            "score": 0.0,
            "failure_distribution": failure_distribution,
            "details": _qa_results,
        }

        # 加权评分
        score = (
            0.20 * report["routing_accuracy"]
            + 0.20 * report["element_hit_rate"]
            + 0.20 * report["local_quality_score"]
            + 0.25 * report["judge_quality_score"]
            + 0.10 * report["language_consistency"]
            + 0.05 * report["critical_error_free_rate"]
        )
        report["score"] = round(score, 4)

        # 落盘
        out = Path("test-results")
        out.mkdir(parents=True, exist_ok=True)
        (out / "qa-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        md_lines = [
            "# QA 问答集评测报告",
            "",
            f"**总用例数**: {total}",
            f"**正例数**: {len(positive_results)}",
            f"**实际执行答案数**: {len(answered_results)}",
            f"**失败用例数**: {len(failed_cases)}",
            "",
            "## 综合评分",
            f"| 指标 | 得分 | 权重 |",
            f"|------|------|------|",
            f"| 路由准确率 | {report['routing_accuracy']:.1%} | 20% |",
            f"| 关键要素命中 | {report['element_hit_rate']:.1%} | 20% |",
            f"| 本地确定性质量 | {report['local_quality_score']:.1%} | 20% |",
            f"| LLM Judge 语义质量 | {report['judge_quality_score']:.1%} | 25% |",
            f"| 语言一致性 | {report['language_consistency']:.1%} | 10% |",
            f"| 严重错误控制 | {report['critical_error_free_rate']:.1%} | 5% |",
            f"| **加权总分** | **{report['score']:.1%}** | |",
            "",
            "## Token 消耗",
            f"- 路由 Token 平均: {report['routing_token_avg'] if report['routing_token_avg'] is not None else '-'}",
            f"- 路由 Token 总计: {report['routing_token_total'] if report['routing_token_total'] is not None else '-'}",
            f"- 执行 Token 平均: {report['token_avg']}",
            f"- 执行 Token 总计: {report['token_total']}",
            "",
            "## 失败原因分布",
            "| 原因 | 数量 |",
            "|------|------|",
        ]
        for reason, count in sorted(failure_distribution.items()):
            md_lines.append(f"| {reason} | {count} |")

        md_lines.extend([
            "",
            "## 明细",
            "| ID | 状态 | 路由 | 要素命中 | 本地质量 | Judge | 中文比 | 幻觉 | 严重问题 | 失败原因 | 路由 Token | 执行 Token |",
            "|----|------|------|---------|----------|-------|--------|------|----------|----------|-----------|-----------|",
        ])
        for r in _qa_results:
            route_ok = "✅" if r["routing_correct"] else "❌"
            routing_token_text = r["routing_tokens"] if r.get("routing_tokens") is not None else "-"
            chinese_ratio = "-" if r.get("chinese_ratio") is None else f"{r['chinese_ratio']:.0%}"
            local_score = "-" if r.get("local_score") is None else f"{r['local_score']:.0%}"
            judge_score = "-" if r.get("judge_score") is None else f"{r['judge_score']:.0%}"
            failures = ",".join(r.get("failure_reasons", [])) or "-"
            warning_count = len(r.get("warnings", []))
            md_lines.append(
                f"| {r['id']} | {r.get('status', '-')} | {route_ok} | {r['must_hits']}/{r['must_total']} | {local_score} | {judge_score} | {chinese_ratio} | {r['hallucination_count']} | {len(r.get('critical_issues', []))}/{warning_count} | {failures} | {routing_token_text} | {r['tokens']} |"
            )
        (out / "qa-report.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")

        assert report["score"] >= 0.5, f"QA 综合评分 {report['score']:.1%} 低于 50%"
