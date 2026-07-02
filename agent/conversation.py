"""多轮 skill 参数补全会话。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from _skill.execution import SkillExecutor
from _skill.models import MatchResult, RedLineViolation, SkillAdapter
from llm.skill_router import LLMSkillCallResult, LLMSkillDecision, OpenAIChatSkillRouter


@dataclass
class SkillConversationState:
    """保存一次未完成 skill 调用的状态。"""

    pending_skill_name: str | None = None
    fields: dict[str, Any] = field(default_factory=dict)
    missing_fields: tuple[str, ...] = ()


class SkillConversationSession:
    """支持“先缺字段拦截，再补字段继续执行”的多轮会话。"""

    def __init__(self, router: OpenAIChatSkillRouter) -> None:
        self.router = router
        self.state = SkillConversationState()

    def handle(
        self,
        user_query: str,
        *,
        adapter: SkillAdapter,
        fields: dict[str, Any] | None = None,
    ) -> LLMSkillCallResult:
        """处理一轮用户输入，并在红线补齐后继续调用 pending skill。"""
        merged_fields = {**self.state.fields, **(fields or {})}
        if self.state.pending_skill_name:
            return self._continue_pending_skill(user_query, adapter=adapter, fields=merged_fields)

        result = self.router.route_and_execute(user_query, adapter=adapter, fields=merged_fields)

        if isinstance(result.activation, RedLineViolation):
            self.state.pending_skill_name = result.activation.skill.name
            self.state.fields = {**merged_fields, **result.decision.fields}
            self.state.missing_fields = tuple(rule.field for rule in result.activation.violated_rules)
            return result

        if result.execution is not None:
            self.state = SkillConversationState()
        return result

    def _continue_pending_skill(
        self,
        user_query: str,
        *,
        adapter: SkillAdapter,
        fields: dict[str, Any],
    ) -> LLMSkillCallResult:
        """继续执行上一轮因红线缺字段而暂停的 skill。"""
        skill = self.router.index.get(self.state.pending_skill_name)
        if skill is None:
            self.state = SkillConversationState()
            decision = LLMSkillDecision(False, None, 0.0, "pending skill 不存在", fields, (), "{}")
            return LLMSkillCallResult(decision=decision, activation=None, execution=None)

        violations = []
        for rule in skill.red_lines:
            value = fields.get(rule.field)
            if value is None or value == "" or value == [] or value == {}:
                violations.append(rule)

        decision = LLMSkillDecision(
            True,
            skill.name,
            1.0,
            "继续上一轮 pending skill",
            fields,
            tuple(rule.field for rule in violations),
            "{}",
        )
        if violations:
            activation = RedLineViolation(
                skill=skill,
                violated_rules=tuple(violations),
                reason="；".join(rule.message for rule in violations),
                confidence=1.0,
            )
            self.state.fields = fields
            self.state.missing_fields = tuple(rule.field for rule in violations)
            return LLMSkillCallResult(decision=decision, activation=activation, execution=None)

        activation = MatchResult(skill=skill, confidence=1.0, redline_pass=True, reason=decision.reason)
        execution = SkillExecutor(self.router.index, adapter).execute(activation, user_query=user_query, fields=fields)
        self.state = SkillConversationState()
        return LLMSkillCallResult(decision=decision, activation=activation, execution=execution)
