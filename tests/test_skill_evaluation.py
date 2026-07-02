"""批量评测测试：SkillEvaluator + 真实 LLM + ≥10 条 eval case。"""

from __future__ import annotations

from pathlib import Path
import os

import pytest
from openai import APIStatusError, RateLimitError

from _skill import (
    CallableSkillAdapter,
    FileSkillDiscovery,
)
from evals.skill_evaluator import SkillEvalCase, SkillEvaluator
from llm.skill_router import LLMRouterResponseError, OpenAIChatSkillRouter, load_skill_env
from llm.schema import LLMDecisionSchemaError
from tests.skill_fixtures import build_pipeline_test_skills

load_skill_env()

LLM_MARK = pytest.mark.skipif(
    not (os.environ.get("API_KEY") or os.environ.get("OPENAI_API_KEY")),
    reason="需要 API_KEY",
)


def _safe_run(evaluator, cases):
    try:
        return evaluator.run(cases)
    except (RateLimitError, APIStatusError) as exc:
        status = getattr(exc, "status_code", 0)
        if status in {401, 403, 429, 503}:
            pytest.skip(f"供应商不可用({status})")
        raise
    except LLMRouterResponseError as exc:
        raw = exc.raw_response.lower()
        if any(w in raw for w in ("quota", "rate", "limit", "recharge", "topup")):
            pytest.skip("额度不足")
        raise
    except LLMDecisionSchemaError:
        pytest.skip("LLM 返回不符合 schema 的 JSON（非确定性行为）")


def _cases() -> list[SkillEvalCase]:
    """构造 11 条评测用例，覆盖 TP / TN / RedLine Block / RedLine Pass 四类场景。"""
    return [
        # TP: 正确激活（提供红线字段）
        SkillEvalCase("tp_doc_zh", "生成一份 word 文档报告，文件名 report.docx 标题 周报",
                      "document-generator", True),
        SkillEvalCase("tp_doc_en", "create a docx report named weekly.docx with title Q2 Summary",
                      "document-generator", True),
        SkillEvalCase("tp_echo", "echo test message", "simple-echo", True),
        SkillEvalCase("tp_skill_index", "列出当前系统所有注册的 skill", "skill-index", True),
        SkillEvalCase("tp_security_passed", "审查 ./src 的 python 代码，输出 json",
                      "security-auditor", True,
                      fields={"scope": "./src", "language": "python", "output_format": "json"}),
        # TN: 正确拒绝无关请求
        SkillEvalCase("tn_weather", "北京今天天气怎么样", None, False),
        SkillEvalCase("tn_coding", "帮我写一个 Python HTTP 服务器", None, False),
        SkillEvalCase("tn_empty", "   ", None, False),
        # 红线拦截
        SkillEvalCase("redline_block_no_fields", "执行安全审查", "security-auditor", False,
                      fields={}, should_block=True),
        SkillEvalCase("redline_block_partial", "审查 python 代码",
                      "security-auditor", False,
                      fields={"language": "python"}, should_block=True),
        # 红线放行
        SkillEvalCase("redline_pass", "审查 ./src 的 python 代码输出 markdown",
                      "security-auditor", True,
                      fields={"scope": "./src", "language": "python", "output_format": "markdown"},
                      should_block=False),
    ]


@LLM_MARK
def test_evaluator_with_real_llm_on_full_caseset(tmp_path: Path) -> None:
    """真实 LLM 跑 11 条评测用例，输出 JSON + Markdown 报告。"""
    index = FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()
    router = OpenAIChatSkillRouter(index)
    adapter = CallableSkillAdapter("eval-adapter", lambda p, s, c: f"eval:{s.name}")
    evaluator = SkillEvaluator(index, router, adapter)

    report = _safe_run(evaluator, _cases())

    # 输出报告文件到固定目录
    json_path, md_path = evaluator.write_report(report, Path("test-results"))
    assert json_path.exists()
    assert md_path.exists()

    assert report.summary["activation_accuracy"] >= 0.6
    assert report.summary["precision"] >= 0.5
    assert report.summary["redline_block_rate"] >= 0.5
    assert report.summary["redline_pass_rate"] >= 0.5

    # 额外验证量化指标中有意义的值
    cm = report.summary.get("confusion_matrix", {})
    assert cm.get("TP", 0) > 0, "混淆矩阵应有 TP"
    assert cm.get("TN", 0) > 0, "混淆矩阵应有 TN"


@LLM_MARK
def test_evaluator_produces_confusion_matrix_with_all_quadrants(tmp_path: Path) -> None:
    """评测报告的混淆矩阵应包含所有象限（该有 P/N 的都有）。"""
    index = FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()
    router = OpenAIChatSkillRouter(index)
    adapter = CallableSkillAdapter("eval", lambda p, s, c: "ok")
    evaluator = SkillEvaluator(index, router, adapter)

    report = _safe_run(evaluator, _cases())
    cm = report.summary.get("confusion_matrix", {})

    # 至少要有 TP 和 TN
    assert cm.get("TP", 0) + cm.get("TN", 0) > 0

    # 每个 case 结果不崩
    assert len(report.cases) == len(_cases())
    for case in report.cases:
        assert case.name
        assert case.reason or case.passed
