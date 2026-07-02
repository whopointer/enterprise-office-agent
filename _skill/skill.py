"""Skill 机制的兼容门面导出。"""

from __future__ import annotations

from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from _skill.activation import SkillActivator
    from _skill.discovery import FileSkillDiscovery
    from _skill.execution import SkillExecutor, TokenTracker
    from _skill.metrics import MetricsCollector
    from _skill.middleware import SkillsMiddleware
    from _skill.parser import parse_skill_file
    from _skill.prompt import format_skills_prompt
    from _skill.models import (
        ActivationStatus,
        CallableSkillAdapter,
        ExecutionContext,
        ExecutionMetrics,
        ExecutionResult,
        MatchResult,
        NoSkillMatched,
        RedLineRule,
        RedLineViolation,
        SkillAdapter,
        SkillAsset,
        SkillDefinition,
        SkillIndex,
        SkillMetricsSpec,
        SkillSource,
        TokenEstimate,
        TokenMetrics,
    )
else:
    from .activation import SkillActivator
    from .discovery import FileSkillDiscovery
    from .execution import SkillExecutor, TokenTracker
    from .metrics import MetricsCollector
    from .middleware import SkillsMiddleware
    from .parser import parse_skill_file
    from .prompt import format_skills_prompt
    from .models import (
        ActivationStatus,
        CallableSkillAdapter,
        ExecutionContext,
        ExecutionMetrics,
        ExecutionResult,
        MatchResult,
        NoSkillMatched,
        RedLineRule,
        RedLineViolation,
        SkillAdapter,
        SkillAsset,
        SkillDefinition,
        SkillIndex,
        SkillMetricsSpec,
        SkillSource,
        TokenEstimate,
        TokenMetrics,
    )

__all__ = [
    "ActivationStatus",
    "CallableSkillAdapter",
    "ExecutionContext",
    "ExecutionMetrics",
    "ExecutionResult",
    "FileSkillDiscovery",
    "MatchResult",
    "MetricsCollector",
    "NoSkillMatched",
    "RedLineRule",
    "RedLineViolation",
    "SkillAdapter",
    "SkillAsset",
    "SkillActivator",
    "SkillDefinition",
    "SkillExecutor",
    "SkillIndex",
    "SkillMetricsSpec",
    "SkillSource",
    "SkillsMiddleware",
    "TokenEstimate",
    "TokenMetrics",
    "TokenTracker",
    "format_skills_prompt",
    "parse_skill_file",
]


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parents[1]
    skills_dir = repo_root / "skills"
    index = FileSkillDiscovery(skills_dir).discover()
    print(
        format_skills_prompt(
            index.list_skills(),
            source_locations=[("skills", str(skills_dir))],
            load_errors=index.load_errors,
        )
    )
