"""Token 统计工具。"""

from __future__ import annotations

from typing import Any

from _skill.models import TokenMetrics


class TokenTracker:
    """Token 统计器；拿不到供应商 usage 时使用字符近似估算。"""

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
        """根据输入输出估算 token 指标。"""
        input_tokens = self.count(prompt)
        output_tokens = self.count(output)
        total_tokens = input_tokens + output_tokens
        return TokenMetrics(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            overhead_pct=self._overhead(total_tokens),
            source="estimated",
        )

    def build_actual_metrics(self, usage: Any) -> TokenMetrics | None:
        """从 OpenAI-compatible usage 对象或 dict 中读取真实 token 指标。"""
        input_tokens = _usage_int(usage, "prompt_tokens", "input_tokens")
        output_tokens = _usage_int(usage, "completion_tokens", "output_tokens")
        total_tokens = _usage_int(usage, "total_tokens")

        if input_tokens is None or output_tokens is None:
            return None
        if total_tokens is None:
            total_tokens = input_tokens + output_tokens

        return TokenMetrics(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            overhead_pct=self._overhead(total_tokens),
            source="actual",
        )

    def _overhead(self, total_tokens: int) -> float | None:
        """计算相对 baseline 的 token 开销。"""
        if self.baseline_tokens and self.baseline_tokens > 0:
            return (total_tokens - self.baseline_tokens) / self.baseline_tokens * 100
        return None


def _usage_int(usage: Any, *keys: str) -> int | None:
    """从 usage 对象中读取整数 token 字段。"""
    if usage is None:
        return None
    for key in keys:
        if isinstance(usage, dict):
            value = usage.get(key)
        else:
            value = getattr(usage, key, None)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None
