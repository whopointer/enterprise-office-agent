"""Execution 阶段：构建 prompt 并调用适配器。"""

from __future__ import annotations

from typing import Any
import json
import logging
import time

from _skill.models import (
    ExecutionContext,
    ExecutionMetrics,
    ExecutionResult,
    SkillAdapter,
    SkillDefinition,
    SkillIndex,
    TokenMetrics,
)

logger = logging.getLogger(__name__)


class TokenTracker:
    """Token 统计器；用字符近似估算。"""

    def __init__(self, *, baseline_tokens: int | None = None):
        self.baseline_tokens = baseline_tokens

    def count(self, text: Any) -> int:
        """估算文本 token 数。"""
        if text is None:
            return 0
        value = str(text)
        if not value:
            return 0
        ascii_chars = sum(1 for char in value if ord(char) < 128)
        non_ascii_chars = len(value) - ascii_chars
        return max(1, round(ascii_chars / 4 + non_ascii_chars / 1.6))

    def build_metrics(self, prompt: str, output: Any) -> TokenMetrics:
        """生成输入、输出与总 token 指标。"""
        input_tokens = self.count(prompt)
        output_tokens = self.count(output)
        total_tokens = input_tokens + output_tokens
        overhead_pct = None
        if self.baseline_tokens and self.baseline_tokens > 0:
            overhead_pct = (total_tokens - self.baseline_tokens) / self.baseline_tokens * 100
        return TokenMetrics(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            overhead_pct=overhead_pct,
        )


class SkillExecutor:
    """Execution 阶段：组装 prompt，调用适配器并记录指标。"""

    def __init__(self, index: SkillIndex, adapter: SkillAdapter, *, token_tracker: TokenTracker | None = None):
        self.index = index
        self.adapter = adapter
        self.token_tracker = token_tracker or TokenTracker()

    def execute(
        self,
        skill: SkillDefinition,
        *,
        user_query: str,
        fields: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        """执行指定 skill。"""
        fields = fields or {}
        prompt = _build_prompt(skill, user_query=user_query, fields=fields)
        start = time.perf_counter()
        success = False
        output: Any = None

        try:
            output = self.adapter.execute(
                prompt,
                skill=skill,
                context={"user_query": user_query, "fields": fields},
            )
            success = True
        except Exception as exc:
            output = {"error": str(exc), "adapter": getattr(self.adapter, "name", self.adapter.__class__.__name__)}
            logger.exception("skill 执行失败: %s", skill.name)
        finally:
            latency_ms = (time.perf_counter() - start) * 1000

        token_metrics = self.token_tracker.build_metrics(prompt, output)

        metrics = ExecutionMetrics(
            token_metrics=token_metrics,
            execution_success=success,
            adapter_name=getattr(self.adapter, "name", self.adapter.__class__.__name__),
            latency_ms=latency_ms,
        )

        return ExecutionResult(
            output=output,
            metrics=metrics,
            context=ExecutionContext(prompt=prompt),
        )


def _build_prompt(
    skill: SkillDefinition,
    *,
    user_query: str,
    fields: dict[str, Any],
) -> str:
    """生成传给适配器的 prompt — 对齐官方格式的渐进披露。"""
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
