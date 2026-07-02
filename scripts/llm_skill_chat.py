"""用真实大模型测试自然语言 skill 路由。"""

from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _skill import CallableSkillAdapter, FileSkillDiscovery, MatchResult, RedLineViolation
from llm.skill_router import OpenAIChatSkillRouter, load_skill_env


def main() -> None:
    """命令行入口。"""
    load_skill_env()
    parser = argparse.ArgumentParser(description="用 OpenAI 大模型测试 skill 路由")
    parser.add_argument("query", help="用户自然语言请求")
    parser.add_argument("--skills-dir", default=None, help="skill 根目录，默认使用仓库 skills")
    parser.add_argument("--model", default=None, help="OpenAI 模型名，默认读取 OPENAI_MODEL 或 gpt-4o-mini")
    parser.add_argument("--field", action="append", default=[], help="结构化字段，格式 key=value，可重复传入")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    skills_dir = Path(args.skills_dir).expanduser().resolve() if args.skills_dir else repo_root / "skills"
    fields = _parse_fields(args.field)

    index = FileSkillDiscovery(skills_dir).discover()
    router = OpenAIChatSkillRouter(index, model=args.model)
    adapter = CallableSkillAdapter("mock-adapter", lambda prompt, skill, context: f"called:{skill.name}")
    result = router.route_and_execute(args.query, adapter=adapter, fields=fields)

    payload = {
        "decision": {
            "should_call": result.decision.should_call,
            "skill_name": result.decision.skill_name,
            "confidence": result.decision.confidence,
            "reason": result.decision.reason,
            "fields": result.decision.fields,
            "missing_fields": list(result.decision.missing_fields),
        },
        "activation": _format_activation(result.activation),
        "execution": _format_execution(result.execution),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _parse_fields(raw_fields: list[str]) -> dict[str, str]:
    """解析 key=value 形式的命令行字段。"""
    fields: dict[str, str] = {}
    for item in raw_fields:
        if "=" not in item:
            raise ValueError(f"--field 必须是 key=value 格式: {item}")
        key, value = item.split("=", 1)
        fields[key.strip()] = value.strip()
    return fields


def _format_activation(activation: MatchResult | RedLineViolation | None) -> dict[str, object] | None:
    """格式化本地激活/红线结果。"""
    if activation is None:
        return None
    if isinstance(activation, RedLineViolation):
        return {
            "type": "RedLineViolation",
            "skill_name": activation.skill.name,
            "reason": activation.reason,
            "violated_fields": [rule.field for rule in activation.violated_rules],
        }
    return {
        "type": "MatchResult",
        "skill_name": activation.skill.name,
        "confidence": activation.confidence,
        "redline_pass": activation.redline_pass,
    }


def _format_execution(execution: object | None) -> dict[str, object] | None:
    """格式化执行结果。"""
    if execution is None:
        return None
    return {
        "output": execution.output,
        "execution_success": execution.metrics.execution_success,
        "adapter_name": execution.metrics.adapter_name,
        "reference_load_rate": execution.metrics.reference_load_rate,
        "asset_load_rate": execution.metrics.asset_load_rate,
        "context_integrity_pass": execution.metrics.context_integrity_pass,
        "asset_paths": list(execution.asset_paths),
    }


if __name__ == "__main__":
    main()
