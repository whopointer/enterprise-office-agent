"""Skill 机制的纯数据结构与适配器协议。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

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


@dataclass(frozen=True)
class ExecutionMetrics:
    """Execution 阶段返回的运行时指标。"""

    token_metrics: TokenMetrics
    execution_success: bool
    adapter_name: str
    latency_ms: float


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


class SkillAdapter(Protocol):
    """框架适配器协议。"""

    name: str

    def execute(self, prompt: str, *, skill: SkillDefinition, context: dict[str, Any]) -> Any:
        """执行已组装好的 prompt。"""


class CallableSkillAdapter:
    """把普通函数包装成 SkillAdapter，用于测试或轻量执行。"""

    def __init__(self, name: str, handler: Callable[[str, SkillDefinition, dict[str, Any]], Any]):
        self.name = name
        self._handler = handler

    def execute(self, prompt: str, *, skill: SkillDefinition, context: dict[str, Any]) -> Any:
        """调用传入的处理函数。"""
        return self._handler(prompt, skill, context)
