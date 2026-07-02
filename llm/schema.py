"""大模型 skill 路由结果的结构校验。"""

from __future__ import annotations

from typing import Any

from _skill.models import SkillIndex


class LLMDecisionSchemaError(ValueError):
    """大模型返回 JSON 结构不符合路由协议。"""


def validate_llm_decision_payload(data: Any, index: SkillIndex) -> dict[str, Any]:
    """校验并规整大模型返回的 skill 选择 JSON。"""
    if not isinstance(data, dict):
        raise LLMDecisionSchemaError("LLM decision 必须是 JSON object")

    should_call = data.get("should_call")
    if not isinstance(should_call, bool):
        raise LLMDecisionSchemaError("should_call 必须是 boolean")

    skill_name = data.get("skill_name")
    if skill_name is not None:
        if not isinstance(skill_name, str):
            raise LLMDecisionSchemaError("skill_name 必须是 string 或 null")
        skill_name = skill_name.strip() or None

    if should_call and not skill_name:
        raise LLMDecisionSchemaError("should_call=true 时必须提供 skill_name")
    if should_call and skill_name not in index.skills:
        raise LLMDecisionSchemaError(f"skill_name 不存在: {skill_name}")

    confidence = data.get("confidence", 0)
    if not isinstance(confidence, (int, float)):
        raise LLMDecisionSchemaError("confidence 必须是 number")
    confidence = max(0.0, min(1.0, float(confidence)))

    fields = data.get("fields", {})
    if not isinstance(fields, dict):
        raise LLMDecisionSchemaError("fields 必须是 object")

    reason = data.get("reason", "")
    if not isinstance(reason, str):
        reason = str(reason)

    return {
        "should_call": should_call,
        "skill_name": skill_name,
        "confidence": confidence,
        "reason": reason.strip(),
        "fields": fields,
    }
