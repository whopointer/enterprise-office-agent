"""用真实大模型测试自然语言 skill 路由。"""

from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _skill import FileSkillDiscovery
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
    decision = router.route(args.query, fields=fields)

    payload = {
        "decision": {
            "should_call": decision.should_call,
            "skill_name": decision.skill_name,
            "confidence": decision.confidence,
            "reason": decision.reason,
            "fields": decision.fields,
        },
        "routing_token_metrics": _format_token_metrics(router.last_token_metrics()),
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


def _format_token_metrics(metrics: object | None) -> dict[str, object] | None:
    """格式化 token 指标。"""
    if metrics is None:
        return None
    return {
        "input_tokens": metrics.input_tokens,
        "output_tokens": metrics.output_tokens,
        "total_tokens": metrics.total_tokens,
        "overhead_pct": metrics.overhead_pct,
        "source": metrics.source,
    }


if __name__ == "__main__":
    main()
