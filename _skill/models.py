"""Skill 机制的纯数据结构与适配器协议。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal, Protocol

SkillSource = str | Path | tuple[str | Path, str]
ActivationStatus = Literal["matched", "no_skill_matched", "redline_violation"]


@dataclass(frozen=True)
class SkillAsset:
    """Skill 声明的资源文件。"""

    path: str
    type: str = "file"
    description: str = ""
    resolved_path: str | None = None
    exists: bool = False


@dataclass(frozen=True)
class RedLineRule:
    """激活前必须满足的红线规则。"""

    field: str
    message: str


@dataclass(frozen=True)
class SkillMetricsSpec:
    """SKILL.md 中声明的测试期望，用于量化评估。"""

    expected_skill: str | None = None
    expected_activation: bool | None = None
    expected_references: tuple[str, ...] = ()
    expected_assets: tuple[str, ...] = ()


@dataclass(frozen=True)
class TokenEstimate:
    """SKILL.md 中声明的 token 估算配置。"""

    system_prompt: int = 0
    per_reference: int = 0
    per_asset: int = 0


@dataclass(frozen=True)
class SkillDefinition:
    """Discovery 阶段产出的单个 skill 纯数据定义。"""

    name: str
    description: str
    path: str
    directory: str
    body: str
    triggers: dict[str, Any] = field(default_factory=dict)
    red_lines: tuple[RedLineRule, ...] = ()
    references: tuple[str, ...] = ()
    assets: tuple[SkillAsset, ...] = ()
    metrics: SkillMetricsSpec = field(default_factory=SkillMetricsSpec)
    token_estimate: TokenEstimate = field(default_factory=TokenEstimate)
    metadata: dict[str, str] = field(default_factory=dict)
    license: str | None = None
    compatibility: str | None = None


@dataclass(frozen=True)
class SkillIndex:
    """Discovery 阶段产出的索引，后续阶段只消费这个纯数据对象。"""

    skills: dict[str, SkillDefinition]
    ref_graph: dict[str, tuple[str, ...]]
    asset_map: dict[str, tuple[SkillAsset, ...]]
    redline_rules: dict[str, tuple[RedLineRule, ...]]
    load_errors: tuple[str, ...] = ()

    def list_skills(self) -> list[SkillDefinition]:
        """按发现顺序返回 skill 列表。"""
        return list(self.skills.values())

    def get(self, name: str) -> SkillDefinition | None:
        """按名称读取 skill。"""
        return self.skills.get(name)


@dataclass(frozen=True)
class MatchResult:
    """Activation 阶段成功激活后的结果。"""

    skill: SkillDefinition
    confidence: float
    redline_pass: bool
    reason: str
    matched_keywords: tuple[str, ...] = ()
    matched_patterns: tuple[str, ...] = ()


@dataclass(frozen=True)
class NoSkillMatched:
    """Activation 阶段没有匹配到任何 skill。"""

    status: ActivationStatus = "no_skill_matched"
    reason: str = "未匹配到可用 skill"
    confidence: float = 0.0


@dataclass(frozen=True)
class RedLineViolation:
    """Activation 阶段命中红线后的拒绝结果。"""

    skill: SkillDefinition
    violated_rules: tuple[RedLineRule, ...]
    reason: str
    confidence: float
    status: ActivationStatus = "redline_violation"


@dataclass(frozen=True)
class TokenMetrics:
    """执行期 token 估算与统计结果。"""

    input_tokens: int
    output_tokens: int
    total_tokens: int
    overhead_pct: float | None = None


@dataclass(frozen=True)
class ExecutionMetrics:
    """Execution 阶段统一返回的量化指标。"""

    token_metrics: TokenMetrics
    reference_load_rate: float
    asset_load_rate: float
    missing_reference_count: int
    missing_asset_count: int
    context_integrity_pass: bool
    execution_success: bool
    adapter_name: str
    latency_ms: float


@dataclass(frozen=True)
class ExecutionContext:
    """Execution 阶段组装后的上下文。"""

    prompt: str
    reference_bodies: dict[str, str]
    assets: tuple[SkillAsset, ...]
    missing_references: tuple[str, ...]
    missing_assets: tuple[str, ...]


@dataclass(frozen=True)
class ExecutionResult:
    """Execution 阶段返回给调用方的结果。"""

    output: Any
    metrics: ExecutionMetrics
    asset_paths: tuple[str, ...]
    context: ExecutionContext


class SkillAdapter(Protocol):
    """框架适配器协议，LangChain 与 SpringAI 只需适配这个接口。"""

    name: str

    def execute(self, prompt: str, *, skill: SkillDefinition, context: dict[str, Any]) -> Any:
        """执行已经组装好的 prompt。"""


class CallableSkillAdapter:
    """把普通函数包装成 SkillAdapter，便于测试或接入轻量执行器。"""

    def __init__(self, name: str, handler: Callable[[str, SkillDefinition, dict[str, Any]], Any]):
        self.name = name
        self._handler = handler

    def execute(self, prompt: str, *, skill: SkillDefinition, context: dict[str, Any]) -> Any:
        """调用传入的处理函数。"""
        return self._handler(prompt, skill, context)
