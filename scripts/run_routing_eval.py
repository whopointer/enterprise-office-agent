"""运行 Skill 路由评测集。"""

from __future__ import annotations

from pathlib import Path
import argparse
import json
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _skill import FileSkillDiscovery
from evals.routing_eval import load_routing_eval_cases, run_routing_eval, write_routing_eval_report
from llm.skill_router import OpenAIChatSkillRouter, load_skill_env


def main() -> None:
    """命令行入口。"""
    parser = argparse.ArgumentParser(description="运行真实 LLM Skill 路由评测集")
    parser.add_argument("--dataset", default="datasets/skill_routing_eval.jsonl")
    parser.add_argument("--skills-dir", default="skills")
    parser.add_argument("--output-dir", default="test-results")
    parser.add_argument("--model", default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    load_skill_env()
    if not (os.environ.get("API_KEY") or os.environ.get("OPENAI_API_KEY")):
        raise RuntimeError("缺少 API_KEY / OPENAI_API_KEY，无法运行真实 LLM 路由评测")

    dataset = _resolve(repo_root, args.dataset)
    skills_dir = _resolve(repo_root, args.skills_dir)
    output_dir = _resolve(repo_root, args.output_dir)
    cases = load_routing_eval_cases(dataset)
    if args.limit is not None:
        cases = cases[: args.limit]

    router = OpenAIChatSkillRouter(FileSkillDiscovery(skills_dir).discover(), model=args.model)
    results, report = run_routing_eval(router, cases)
    json_path, md_path = write_routing_eval_report(results, report, output_dir)
    print(json.dumps({"json": str(json_path), "markdown": str(md_path), "summary": report}, ensure_ascii=False, indent=2))


def _resolve(repo_root: Path, raw: str) -> Path:
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    return repo_root / path


if __name__ == "__main__":
    main()
