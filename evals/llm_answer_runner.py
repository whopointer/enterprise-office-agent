"""QA 评测专用 LLM 答案生成器。

该模块只服务自动化评测，不是正式 agent 执行层。正式 skill 机制应由 agent
读取 SKILL.md 后自行调用工具；这里为了 QA 数据集测试，需要固定方式生成答案。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import json
import time

from openai import OpenAI

from _skill.models import ExecutionMetrics, SkillDefinition
from core.token_tracker import TokenTracker
from llm.skill_router import _build_openai_client, load_skill_env


@dataclass(frozen=True)
class LLMAnswerResult:
    """一次 QA 评测答案生成结果。"""

    output: str
    prompt: str
    metrics: ExecutionMetrics


class EvalLLMAnswerRunner:
    """评测专用 OpenAI-compatible LLM runner。"""

    name = "EvalLLMAnswerRunner"

    def __init__(
        self,
        *,
        model: str | None = None,
        client: OpenAI | None = None,
        token_tracker: TokenTracker | None = None,
    ) -> None:
        load_skill_env()
        import os

        self.model = model or os.environ.get("MODEL") or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        self.client = client or _build_openai_client()
        self.token_tracker = token_tracker or TokenTracker()

    def run(self, skill: SkillDefinition, *, user_query: str, fields: dict[str, Any] | None = None) -> LLMAnswerResult:
        """根据 skill 和用户问题生成 QA 评测答案。"""
        fields = fields or {}
        prompt = build_eval_skill_prompt(skill, user_query=user_query, fields=fields)
        start = time.perf_counter()
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0.2,
            messages=[
                {"role": "system", "content": f"你正在执行 QA 评测中的 skill: {skill.name}。请严格遵循上下文。"},
                {"role": "user", "content": prompt},
            ],
        )
        latency_ms = (time.perf_counter() - start) * 1000
        output = response.choices[0].message.content or ""
        token_metrics = self.token_tracker.build_actual_metrics(getattr(response, "usage", None))
        if token_metrics is None:
            token_metrics = self.token_tracker.build_metrics(prompt, output)
        return LLMAnswerResult(
            output=output,
            prompt=prompt,
            metrics=ExecutionMetrics(
                token_metrics=token_metrics,
                execution_success=True,
                runner_name=self.name,
                latency_ms=latency_ms,
            ),
        )

    def judge_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        """调用 LLM judge，要求返回 JSON object。"""
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "你是严格的软件工程答案质量评测员，只输出 JSON。"},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
        )
        raw = response.choices[0].message.content or "{}"
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {"overall": 0, "critical_issues": ["judge 返回非 JSON"], "reason": raw}
        parsed["_token_usage"] = getattr(response, "usage", None)
        return parsed


def build_eval_skill_prompt(skill: SkillDefinition, *, user_query: str, fields: dict[str, Any]) -> str:
    """生成 QA 评测用 prompt；不作为正式 agent 架构的一部分。"""
    lines = [
        f"# Skill: {skill.name}",
        "",
        "## Skill 描述",
        skill.description,
        "",
        "## 用户请求",
        user_query,
        "",
        "## 结构化字段",
        json.dumps(fields, ensure_ascii=False, indent=2),
        "",
        "## Skill 指令",
        skill.body,
    ]
    return "\n".join(lines)
