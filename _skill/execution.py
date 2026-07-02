"""Execution 阶段：上下文装载、适配器调用与执行指标。"""

from __future__ import annotations

from typing import Any
import json
import logging
import time

from .models import (
    ExecutionContext,
    ExecutionMetrics,
    ExecutionResult,
    MatchResult,
    SkillAdapter,
    SkillDefinition,
    SkillIndex,
    TokenMetrics,
)
from .utils import safe_rate

logger = logging.getLogger(__name__)


class TokenTracker:
    """Token 统计器；当前用字符近似估算，后续可替换为模型 tokenizer。"""

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
    """Execution 阶段：装载 reference 与 asset，调用适配器并记录指标。"""

    def __init__(self, index: SkillIndex, adapter: SkillAdapter, *, token_tracker: TokenTracker | None = None):
        self.index = index
        self.adapter = adapter
        self.token_tracker = token_tracker or TokenTracker()

    def execute(
        self,
        match: MatchResult,
        *,
        user_query: str,
        fields: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        """执行已激活的 skill。"""
        fields = fields or {}
        context = self.build_context(match.skill, user_query=user_query, fields=fields)
        start = time.perf_counter()
        success = False
        output: Any = None

        try:
            output = self.adapter.execute(
                context.prompt,
                skill=match.skill,
                context={"user_query": user_query, "fields": fields, "execution_context": context},
            )
            success = True
        except Exception as exc:
            output = {"error": str(exc), "adapter": getattr(self.adapter, "name", self.adapter.__class__.__name__)}
            logger.exception("skill 执行失败: %s", match.skill.name)
        finally:
            latency_ms = (time.perf_counter() - start) * 1000

        token_metrics = self.token_tracker.build_metrics(context.prompt, output)
        total_refs = len(match.skill.references)
        total_assets = len(match.skill.assets)
        loaded_refs = total_refs - len(context.missing_references)
        loaded_assets = total_assets - len(context.missing_assets)

        metrics = ExecutionMetrics(
            token_metrics=token_metrics,
            reference_load_rate=safe_rate(loaded_refs, total_refs),
            asset_load_rate=safe_rate(loaded_assets, total_assets),
            missing_reference_count=len(context.missing_references),
            missing_asset_count=len(context.missing_assets),
            context_integrity_pass=not context.missing_references and not context.missing_assets,
            execution_success=success,
            adapter_name=getattr(self.adapter, "name", self.adapter.__class__.__name__),
            latency_ms=latency_ms,
        )

        return ExecutionResult(
            output=output,
            metrics=metrics,
            asset_paths=tuple(asset.resolved_path or asset.path for asset in context.assets),
            context=context,
        )

    def build_context(self, skill: SkillDefinition, *, user_query: str, fields: dict[str, Any]) -> ExecutionContext:
        """按照渐进式披露原则组装执行上下文。"""
        reference_bodies: dict[str, str] = {}
        missing_references: list[str] = []
        missing_assets: list[str] = []

        for reference_name in skill.references:
            reference = self.index.get(reference_name)
            if reference is None:
                missing_references.append(reference_name)
                continue
            reference_bodies[reference_name] = reference.body

        for asset in skill.assets:
            if not asset.exists:
                missing_assets.append(asset.path)

        prompt = self._build_prompt(
            skill,
            user_query=user_query,
            fields=fields,
            reference_bodies=reference_bodies,
            missing_references=missing_references,
            missing_assets=missing_assets,
        )

        return ExecutionContext(
            prompt=prompt,
            reference_bodies=reference_bodies,
            assets=skill.assets,
            missing_references=tuple(missing_references),
            missing_assets=tuple(missing_assets),
        )

    def _build_prompt(
        self,
        skill: SkillDefinition,
        *,
        user_query: str,
        fields: dict[str, Any],
        reference_bodies: dict[str, str],
        missing_references: list[str],
        missing_assets: list[str],
    ) -> str:
        """生成传给框架适配器的 prompt。"""
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

        if reference_bodies:
            lines.extend(["", "## Reference 展开"])
            for name, body in reference_bodies.items():
                lines.extend([f"### {name}", body])

        if skill.assets:
            lines.extend(["", "## Asset 注入"])
            for asset in skill.assets:
                lines.append(
                    f"- path={asset.path}; type={asset.type}; exists={asset.exists}; "
                    f"resolved_path={asset.resolved_path}; description={asset.description}"
                )

        if missing_references or missing_assets:
            lines.extend(["", "## 上下文缺失项"])
            for name in missing_references:
                lines.append(f"- missing_reference: {name}")
            for path in missing_assets:
                lines.append(f"- missing_asset: {path}")

        return "\n".join(lines)
