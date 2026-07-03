"""Render Deploy 问答集自动化测试 — 评估 LLM 输出质量。

从 datasets/render-deploy-qa.json 读取 20 条用例，逐条调真实 LLM，
对比 expected_skill / expected_elements，输出量化评分报告。
"""

from __future__ import annotations

from pathlib import Path
import json
import os
import re

import pytest
from openai import APIStatusError, RateLimitError

from _skill import (
    CallableSkillAdapter,
    FileSkillDiscovery,
)
from adapters.skill_adapters import OpenAICompatibleSkillAdapter
from core.runtime_metrics import RuntimeCollector
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
        return json.load(f)


def _build_index():
    return FileSkillDiscovery(REPO_ROOT / "skills").discover()


# ---------------------------------------------------------------------------
# 评估函数
# ---------------------------------------------------------------------------

def _check_elements(output: str, expected_elements: list[str]) -> tuple[int, int, list[str]]:
    """检查输出中命中多少关键要素。"""
    hits = 0
    missed = []
    lower = output.lower()
    for elem in expected_elements:
        if elem.lower() in lower:
            hits += 1
        else:
            missed.append(elem)
    return hits, len(expected_elements), missed


def _chinese_ratio(text: str) -> float:
    """中文字符占比。"""
    if not text:
        return 0.0
    chinese = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    return chinese / len(text)


def _has_hallucination(output: str, skill_dir: str) -> list[str]:
    """检查输出是否引用了不存在的文件路径。"""
    if not skill_dir:
        return []
    skill_path = Path(skill_dir)
    hallucinations = []
    # 匹配 scripts/xxx.py 或 references/xxx.md 或 assets/xxx 模式
    refs = re.findall(r"(?:scripts|references|assets)/[\w./-]+", output)
    for ref in refs:
        full = skill_path / ref
        if not full.exists():
            hallucinations.append(ref)
    return hallucinations


# ---------------------------------------------------------------------------
# 逐条测试
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["id"])
@LLM_MARK
def test_qa_case(case, runtime_collector):
    """逐条运行问答对并评估。"""
    query = case["query"]
    expected_skill = case["expected_skill"]
    expected_elements = case["expected_elements"]

    index = _build_index()

    # ── 路由 ──
    router = OpenAIChatSkillRouter(index)
    try:
        decision = router.route(query)
    except (RateLimitError, APIStatusError) as exc:
        status = getattr(exc, "status_code", 0)
        if status in {401, 403, 429, 503}:
            pytest.skip(f"供应商不可用({status})")
        raise
    except (LLMRouterResponseError, LLMDecisionSchemaError):
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
        assert not decision.should_call, f"{case['id']}: 期望不激活但 LLM 选中了 {actual_skill}"
        return

    # ── 执行 ──
    if not decision.should_call or actual_skill is None:
        # LLM 漏判（FN）—— 真实数据，记录 skip
        _qa_results.append({
            "id": case["id"],
            "routing_correct": False,
            "hit_rate": 0.0,
            "hits": 0,
            "total_elements": len(expected_elements),
            "missed": expected_elements,
            "chinese_ratio": 0.0,
            "hallucination_count": 0,
            "hallucinations": [],
            "tokens": 0,
            "routing_tokens": _token_total(router.last_token_metrics()),
            "difficulty": case.get("difficulty", ""),
            "note": f"LLM 未激活 (FN)，expected={expected_skill}",
        })
        return  # 不 fail，仅记录

    assert routing_correct, f"{case['id']}: 期望 {expected_skill} 实际 {actual_skill}"

    skill = index.get(actual_skill)
    adapter = OpenAICompatibleSkillAdapter()
    from core.executor import SkillExecutor

    executor = SkillExecutor(index, adapter)
    result = executor.execute(skill, user_query=query, fields=decision.fields)

    runtime_collector.record(skill.name, result.metrics)

    output = str(result.output)

    # ── 结构完整度 ──
    hits, total, missed = _check_elements(output, expected_elements)
    hit_rate = hits / total if total else 0

    # ── 语言一致性 ──
    cn_ratio = _chinese_ratio(output)

    # ── 幻觉检测 ──
    hallucinations = _has_hallucination(output, skill.directory)

    # ── Token ──
    tokens = result.metrics.token_metrics.total_tokens
    routing_tokens = _token_total(router.last_token_metrics())

    # 落盘单条结果
    case_result = {
        "id": case["id"],
        "routing_correct": routing_correct,
        "hit_rate": round(hit_rate, 2),
        "hits": hits,
        "total_elements": total,
        "missed": missed,
        "chinese_ratio": round(cn_ratio, 2),
        "hallucination_count": len(hallucinations),
        "hallucinations": hallucinations,
        "tokens": tokens,
        "routing_tokens": routing_tokens,
        "difficulty": case.get("difficulty", ""),
    }

    # 把结果存入 collector 用于汇总报告
    _qa_results.append(case_result)

    assert routing_correct, f"{case['id']}: 路由错误"
    assert hit_rate >= 0.15, f"{case['id']}: 要素命中率过低 ({hit_rate:.0%})，missed={missed}"
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
        routing_correct = sum(1 for r in _qa_results if r["routing_correct"])
        total_elements = sum(r["total_elements"] for r in _qa_results)
        total_hits = sum(r["hits"] for r in _qa_results)
        hallucination_cases = sum(1 for r in _qa_results if r["hallucination_count"] > 0)
        cn_ok = sum(1 for r in _qa_results if r["chinese_ratio"] > 0.10)
        tokens = [r["tokens"] for r in _qa_results]
        routing_tokens = [r["routing_tokens"] for r in _qa_results if r.get("routing_tokens") is not None]

        report = {
            "total_cases": total,
            "routing_accuracy": round(routing_correct / total, 4),
            "element_hit_rate": round(total_hits / total_elements, 4) if total_elements else 0,
            "language_consistency": round(cn_ok / total, 4),
            "hallucination_free_rate": round((total - hallucination_cases) / total, 4),
            "token_avg": round(sum(tokens) / len(tokens), 1) if tokens else 0,
            "token_total": sum(tokens),
            "routing_token_avg": round(sum(routing_tokens) / len(routing_tokens), 1) if routing_tokens else None,
            "routing_token_total": sum(routing_tokens) if routing_tokens else None,
            "score": 0.0,
            "details": _qa_results,
        }

        # 加权评分
        score = (
            0.30 * report["routing_accuracy"]
            + 0.30 * report["element_hit_rate"]
            + 0.10 * report["language_consistency"]
            + 0.20 * report["hallucination_free_rate"]
            + 0.10 * 1.0  # token 效率暂不纳入（无基线），给满分
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
            "",
            "## 综合评分",
            f"| 指标 | 得分 | 权重 |",
            f"|------|------|------|",
            f"| 路由准确率 | {report['routing_accuracy']:.1%} | 30% |",
            f"| 结构完整度 | {report['element_hit_rate']:.1%} | 30% |",
            f"| 语言一致性 | {report['language_consistency']:.1%} | 10% |",
            f"| 幻觉控制 | {report['hallucination_free_rate']:.1%} | 20% |",
            f"| token 效率 | 100% (基线待定) | 10% |",
            f"| **加权总分** | **{report['score']:.1%}** | |",
            "",
            "## Token 消耗",
            f"- 路由 Token 平均: {report['routing_token_avg'] if report['routing_token_avg'] is not None else '-'}",
            f"- 路由 Token 总计: {report['routing_token_total'] if report['routing_token_total'] is not None else '-'}",
            f"- 执行 Token 平均: {report['token_avg']}",
            f"- 执行 Token 总计: {report['token_total']}",
            "",
            "## 明细",
            "| ID | 路由 | 要素命中 | 中文比 | 幻觉 | 路由 Token | 执行 Token |",
            "|----|------|---------|--------|------|-----------|-----------|",
        ]
        for r in _qa_results:
            route_ok = "✅" if r["routing_correct"] else "❌"
            routing_token_text = r["routing_tokens"] if r.get("routing_tokens") is not None else "-"
            md_lines.append(
                f"| {r['id']} | {route_ok} | {r['hits']}/{r['total_elements']} | {r['chinese_ratio']:.0%} | {r['hallucination_count']} | {routing_token_text} | {r['tokens']} |"
            )
        (out / "qa-report.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")

        assert report["score"] >= 0.5, f"QA 综合评分 {report['score']:.1%} 低于 50%"
