"""MetricsCollector 综合量化指标测试。"""

from __future__ import annotations

from pathlib import Path
import json

from _skill import (
    CallableSkillAdapter,
    FileSkillDiscovery,
    MatchResult,
    MetricsCollector,
    NoSkillMatched,
    RedLineViolation,
    SkillActivator,
    SkillExecutor,
    TokenTracker,
)
from tests.skill_fixtures import build_pipeline_test_skills


def test_metrics_collector_comprehensive_report(tmp_path: Path) -> None:
    """MetricsCollector 应产出 DESIGN.md 要求的调用、红线、执行与适配器指标。"""
    index = FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()
    activator = SkillActivator(index)
    collector = MetricsCollector()

    # 基线 token
    baseline_skill = index.get("simple-echo")
    baseline_match = activator.activate("echo ping")
    assert isinstance(baseline_match, MatchResult)
    baseline_result = SkillExecutor(
        index,
        CallableSkillAdapter("SpringAI", lambda p, s, c: "baseline"),
    ).execute(baseline_match, user_query="echo ping")
    baseline_tokens = baseline_result.metrics.token_metrics.total_tokens

    # Token overhead 对比
    token_tracker = TokenTracker(baseline_tokens=baseline_tokens)
    doc_match = activator.activate("生成 word 文档",
                                   fields={"filename": "r.docx", "title": "周报"})
    assert isinstance(doc_match, MatchResult)
    doc_result = SkillExecutor(
        index,
        CallableSkillAdapter("LangChain", lambda p, s, c: "word-output"),
        token_tracker=token_tracker,
    ).execute(doc_match, user_query="生成 word 文档")

    # 匹配场景
    index_match = activator.activate("列出所有注册 skill")
    assert isinstance(index_match, MatchResult)

    no_match = activator.activate("今天天气")
    assert isinstance(no_match, NoSkillMatched)

    blocked = activator.activate("执行安全检查")
    assert isinstance(blocked, RedLineViolation)

    passed = activator.activate("安全检查", fields={
        "scope": "./src", "language": "python", "output_format": "json",
    })
    assert isinstance(passed, MatchResult)

    # 记录 — 红线拦截的 skill 视为未激活（expected_activation=False）
    collector.record_activation(doc_match, expected_skill="document-generator", expected_activation=True)
    collector.record_activation(index_match, expected_skill="skill-index", expected_activation=True)
    collector.record_activation(no_match, expected_skill=None, expected_activation=False)
    collector.record_activation(blocked, expected_skill=None, expected_activation=False)
    collector.record_activation(passed, expected_skill="security-auditor", expected_activation=True)

    collector.record_redline(blocked, should_block=True, expected_reason="缺少审查范围")
    collector.record_redline(passed, should_block=False)

    collector.record_execution(baseline_result)
    collector.record_execution(doc_result)

    report = collector.report()

    assert doc_result.metrics.token_metrics.overhead_pct is not None
    assert report["activation_accuracy"] == 1.0
    assert report["precision"] == 1.0
    assert report["recall"] == 1.0
    assert report["confusion_matrix"]["TP"] == 3
    assert report["confusion_matrix"]["TN"] == 2
    assert report["redline_block_rate"] == 1.0
    assert report["redline_pass_rate"] == 1.0
    assert report["execution_success_rate"] == 1.0
    assert "SpringAI" in report["adapter_success_rate"]
    assert "LangChain" in report["adapter_success_rate"]

    # 落盘量化指标报告
    output_dir = Path("test-results")
    output_dir.mkdir(parents=True, exist_ok=True)

    # 补充 token 对比数据
    report["token_comparison"] = {
        "baseline_simple_echo": baseline_tokens,
        "document_generator": doc_result.metrics.token_metrics.total_tokens,
        "overhead_pct": doc_result.metrics.token_metrics.overhead_pct,
    }

    (output_dir / "metrics-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # Markdown 版
    md_lines = [
        "# 量化指标报告 (MetricsCollector)",
        "",
        "## 路由准确度",
        f"- activation_accuracy: {report['activation_accuracy']:.1%}",
        f"- precision: {report['precision']:.1%}",
        f"- recall: {report['recall']:.1%}",
        f"- 混淆矩阵: TP={report['confusion_matrix']['TP']} TN={report['confusion_matrix']['TN']} FP={report['confusion_matrix']['FP']} FN={report['confusion_matrix']['FN']}",
        "",
        "## 红线质量",
        f"- 拦截率: {report['redline_block_rate']:.1%}",
        f"- 放行率: {report['redline_pass_rate']:.1%}",
        f"- 误拦率: {report['redline_false_block_rate']:.1%}",
        f"- reason 匹配率: {report['redline_reason_match_rate']:.1%}",
        "",
        "## 执行质量",
        f"- 执行成功率: {report['execution_success_rate']:.1%}",
        f"- 适配器成功率: {report['adapter_success_rate']}",
        f"- 产物成功率: {report['artifact_success_rate']:.1%}",
        "",
        "## Token 消耗对比",
        f"- 基线 (simple-echo): {report['token_comparison']['baseline_simple_echo']} tokens",
        f"- 文档生成 (document-generator): {report['token_comparison']['document_generator']} tokens",
        f"- overhead: {report['token_comparison']['overhead_pct']:.1f}%",
    ]
    (output_dir / "metrics-report.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")
