"""Skill 机制的纯数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SkillSource = str | Path | tuple[str | Path, str]


@dataclass(frozen=True)
class SkillDefinition:
    """单个 skill 的纯数据定义，对齐官方 SKILL.md 格式（name + description + allowed-tools + body）。"""

    name: str
    description: str
    path: str
    directory: str
    body: str
    allowed_tools: tuple[str, ...] = ()
    license: str | None = None
    compatibility: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SkillIndex:
    """Discovery 阶段产出的索引。"""

    skills: dict[str, SkillDefinition]
    load_errors: tuple[str, ...] = ()

    def list_skills(self) -> list[SkillDefinition]:
        """按发现顺序返回 skill 列表。"""
        return list(self.skills.values())

    def get(self, name: str) -> SkillDefinition | None:
        """按名称读取 skill。"""
        return self.skills.get(name)


@dataclass(frozen=True)
class TokenMetrics:
    """执行期 token 估算与统计结果。"""

    input_tokens: int
    output_tokens: int
    total_tokens: int
    overhead_pct: float | None = None
    source: str = "estimated"


@dataclass(frozen=True, init=False)
class ExecutionMetrics:
    """运行时指标，适用于 eval runner 或真实工具调用。"""

    token_metrics: TokenMetrics
    execution_success: bool
    runner_name: str
    latency_ms: float

    def __init__(
        self,
        token_metrics: TokenMetrics,
        execution_success: bool,
        runner_name: str | None = None,
        latency_ms: float = 0.0,
        adapter_name: str | None = None,
    ) -> None:
        """兼容旧的 adapter_name 入参，新代码应使用 runner_name。"""
        object.__setattr__(self, "token_metrics", token_metrics)
        object.__setattr__(self, "execution_success", execution_success)
        object.__setattr__(self, "runner_name", runner_name or adapter_name or "unknown")
        object.__setattr__(self, "latency_ms", latency_ms)

    @property
    def adapter_name(self) -> str:
        """兼容旧报告代码的只读别名。"""
        return self.runner_name


@dataclass(frozen=True)
class ExecutionContext:
    """Execution 阶段组装后的上下文。"""

    prompt: str


@dataclass(frozen=True)
class ExecutionResult:
    """Execution 阶段返回给调用方的结果。"""

    output: Any
    metrics: ExecutionMetrics
    context: ExecutionContext
