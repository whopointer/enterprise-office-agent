"""RuntimeCollector 量化指标报告测试。"""

from __future__ import annotations

from _skill.models import ExecutionMetrics, TokenMetrics
from core.runtime_metrics import RuntimeCollector


def _metrics(adapter: str, total_tokens: int, latency_ms: float, success: bool = True) -> ExecutionMetrics:
    return ExecutionMetrics(
        token_metrics=TokenMetrics(
            input_tokens=total_tokens - 3,
            output_tokens=3,
            total_tokens=total_tokens,
            source="estimated",
        ),
        execution_success=success,
        adapter_name=adapter,
        latency_ms=latency_ms,
    )


def test_token_tracker_builds_actual_metrics_from_usage_object() -> None:
    """TokenTracker 应能从 OpenAI usage 对象生成真实 token 指标。"""
    from core.executor import TokenTracker

    class Usage:
        prompt_tokens = 12
        completion_tokens = 5
        total_tokens = 17

    metrics = TokenTracker().build_actual_metrics(Usage())

    assert metrics is not None
    assert metrics.input_tokens == 12
    assert metrics.output_tokens == 5
    assert metrics.total_tokens == 17
    assert metrics.source == "actual"


def test_token_tracker_builds_actual_metrics_from_usage_dict() -> None:
    """TokenTracker 应兼容 dict 形式的 usage。"""
    from core.executor import TokenTracker

    metrics = TokenTracker().build_actual_metrics({"input_tokens": 9, "output_tokens": 4})

    assert metrics is not None
    assert metrics.input_tokens == 9
    assert metrics.output_tokens == 4
    assert metrics.total_tokens == 13
    assert metrics.source == "actual"


def test_runtime_collector_reports_execution_groups_and_latency() -> None:
    """执行指标应支持总体、按 skill、按 adapter 分组统计。"""
    collector = RuntimeCollector()
    collector.record("simple-echo", _metrics("callable", 10, 1.0))
    collector.record("simple-echo", _metrics("callable", 20, 3.0))
    collector.record("document-generator", _metrics("word", 30, 5.0, success=False))

    report = collector.report()

    assert report["total_executions"] == 3
    assert report["success_count"] == 2
    assert report["success_rate"] == 0.6667
    assert report["token_consumption"] == {"min": 10, "max": 30, "avg": 20.0, "total": 60}
    assert report["token_source_counts"] == {"estimated": 3}
    assert report["latency_ms"]["min"] == 1.0
    assert report["latency_ms"]["max"] == 5.0
    assert report["latency_ms"]["p50"] == 3.0
    assert report["by_skill"]["simple-echo"]["count"] == 2
    assert report["by_adapter"]["callable"]["success_rate"] == 1.0
    assert report["by_adapter"]["word"]["success_rate"] == 0.0


def test_runtime_collector_reports_confusion_matrix() -> None:
    """路由评估应输出 TP/TN/FP/FN 与准确率指标。"""
    collector = RuntimeCollector()
    collector.record_routing("生成报告", "document-generator", "document-generator", True, True)
    collector.record_routing("天气", None, None, False, False)
    collector.record_routing("写代码", None, "code-reviewer", False, True)
    collector.record_routing("分析数据", "data-analyzer", None, True, False)

    report = collector.report()

    assert report["confusion_matrix"] == {"TP": 1, "TN": 1, "FP": 1, "FN": 1}
    assert report["activation_accuracy"] == 0.5
    assert report["precision"] == 0.5
    assert report["recall"] == 0.5
    assert report["routing_eval_scope"]["sample_count"] == 4
    assert len(report["eval_details"]) == 4


def test_runtime_collector_reports_routing_token_metrics() -> None:
    """路由记录带真实 token 时，应输出路由 token 汇总和来源。"""
    collector = RuntimeCollector()
    collector.record_routing(
        "生成报告",
        "document-generator",
        "document-generator",
        True,
        True,
        token_metrics=TokenMetrics(input_tokens=30, output_tokens=8, total_tokens=38, source="actual"),
    )
    collector.record_routing(
        "天气",
        None,
        None,
        False,
        False,
        token_metrics=TokenMetrics(input_tokens=20, output_tokens=5, total_tokens=25, source="actual"),
    )

    report = collector.report()

    assert report["routing_token_consumption"] == {"min": 25, "max": 38, "avg": 31.5, "total": 63}
    assert report["routing_token_source_counts"] == {"actual": 2}
    assert report["eval_details"][0]["total_tokens"] == 38


def test_runtime_collector_writes_json_and_markdown(tmp_path) -> None:
    """量化报告应能落盘为 JSON 和 Markdown。"""
    collector = RuntimeCollector()
    collector.record("simple-echo", _metrics("callable", 10, 1.0))
    collector.record_routing("ping", "simple-echo", "simple-echo", True, True)

    json_path, md_path = collector.write_report(tmp_path)

    assert json_path.exists()
    assert md_path.exists()
    assert "confusion_matrix" in json_path.read_text(encoding="utf-8")
    markdown = md_path.read_text(encoding="utf-8")
    assert "Skill Pipeline pytest 运行时量化报告" in markdown
    assert "不等同于 `routing-eval-report.*` 的大样本评测" in markdown


def test_runtime_collector_writes_routing_token_markdown(tmp_path) -> None:
    """Markdown 报告应展示路由 token 消耗。"""
    collector = RuntimeCollector()
    collector.record_routing(
        "ping",
        "simple-echo",
        "simple-echo",
        True,
        True,
        token_metrics=TokenMetrics(input_tokens=10, output_tokens=4, total_tokens=14, source="actual"),
    )

    _, md_path = collector.write_report(tmp_path)

    markdown = md_path.read_text(encoding="utf-8")
    assert "## 路由 Token 消耗" in markdown
    assert "| 累计总消耗 | 14 |" in markdown


def test_runtime_collector_empty_report_is_empty() -> None:
    """无记录时报告为空 dict。"""
    assert RuntimeCollector().report() == {}


def test_runtime_collector_only_eval_records() -> None:
    """只有路由评估记录时也应输出混淆矩阵。"""
    collector = RuntimeCollector()
    collector.record_routing("天气", None, None, False, False)

    report = collector.report()

    assert "total_executions" not in report
    assert report["confusion_matrix"] == {"TP": 0, "TN": 1, "FP": 0, "FN": 0}
    assert report["precision"] == 1.0
    assert report["recall"] == 1.0


def test_runtime_collector_p95_for_twenty_records() -> None:
    """记录数 >=20 时应计算 p95。"""
    collector = RuntimeCollector()
    for index in range(20):
        collector.record("skill", _metrics("adapter", total_tokens=10 + index, latency_ms=float(index)))

    report = collector.report()

    assert report["latency_ms"]["p95"] == 19.0
    assert report["token_consumption"]["min"] == 10
    assert report["token_consumption"]["max"] == 29


def test_runtime_collector_skill_mismatch_counts_as_fp() -> None:
    """预期激活但选错 skill 应计为 FP。"""
    collector = RuntimeCollector()
    collector.record_routing("生成报告", "document-generator", "code-reviewer", True, True)

    report = collector.report()

    assert report["confusion_matrix"] == {"TP": 0, "TN": 0, "FP": 1, "FN": 0}
    assert report["precision"] == 0.0
    assert report["recall"] == 1.0


def test_runtime_collector_large_record_set_groups_are_stable() -> None:
    """较多记录下按 skill/adapter 分组应保持稳定。"""
    collector = RuntimeCollector()
    for index in range(100):
        collector.record(f"skill-{index % 5}", _metrics(f"adapter-{index % 4}", 50 + index, float(index), success=index % 10 != 0))

    report = collector.report()

    assert report["total_executions"] == 100
    assert len(report["by_skill"]) == 5
    assert len(report["by_adapter"]) == 4
    assert report["success_count"] == 90
    assert report["success_rate"] == 0.9
