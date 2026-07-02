"""接入大模型的自然语言 skill 路由。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json
import os
from urllib.parse import urlparse

from dotenv import load_dotenv
from openai import OpenAI

from _skill.execution import SkillExecutor
from _skill.models import ExecutionResult, MatchResult, RedLineRule, RedLineViolation, SkillAdapter, SkillIndex
from .schema import validate_llm_decision_payload
from agent.field_extractor import extract_fields_from_query


@dataclass(frozen=True)
class LLMSkillDecision:
    """大模型对自然语言请求的 skill 选择结果。"""

    should_call: bool
    skill_name: str | None
    confidence: float
    reason: str
    fields: dict[str, Any]
    missing_fields: tuple[str, ...]
    raw_response: str


@dataclass(frozen=True)
class LLMSkillCallResult:
    """大模型路由后，本地执行器的调用结果。"""

    decision: LLMSkillDecision
    activation: MatchResult | RedLineViolation | None
    execution: ExecutionResult | None


class LLMRouterResponseError(RuntimeError):
    """大模型响应不是预期 JSON 时抛出。"""

    def __init__(self, raw_response: str):
        self.raw_response = raw_response
        super().__init__(f"大模型未返回合法 JSON: {raw_response[:200]}")


class OpenAIChatSkillRouter:
    """用 OpenAI Chat Completions 测试自然语言到 skill 的路由。"""

    def __init__(
        self,
        index: SkillIndex,
        *,
        model: str | None = None,
        client: OpenAI | None = None,
    ) -> None:
        load_skill_env()
        self.index = index
        self.model = model or os.environ.get("MODEL") or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        self.client = client or _build_openai_client()

    def route(self, user_query: str, *, fields: dict[str, Any] | None = None) -> LLMSkillDecision:
        """让大模型根据 skill 目录和用户自然语言选择一个 skill。"""
        fields = {**extract_fields_from_query(user_query), **(fields or {})}
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": self._build_system_prompt()},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"user_query": user_query, "known_fields": fields},
                        ensure_ascii=False,
                    ),
                },
            ],
        )
        raw = response.choices[0].message.content or "{}"
        return self._parse_decision(raw, fallback_fields=fields)

    def route_and_execute(
        self,
        user_query: str,
        *,
        adapter: SkillAdapter,
        fields: dict[str, Any] | None = None,
    ) -> LLMSkillCallResult:
        """让大模型选 skill，再由本地红线校验和执行器完成调用。"""
        decision = self.route(user_query, fields=fields)
        if not decision.should_call or not decision.skill_name:
            return LLMSkillCallResult(decision=decision, activation=None, execution=None)

        skill = self.index.get(decision.skill_name)
        if skill is None:
            return LLMSkillCallResult(decision=decision, activation=None, execution=None)

        merged_fields = {**(fields or {}), **decision.fields}
        violations = _check_red_lines(skill.red_lines, merged_fields)
        if violations:
            activation = RedLineViolation(
                skill=skill,
                violated_rules=tuple(violations),
                reason="；".join(rule.message for rule in violations),
                confidence=decision.confidence,
            )
            return LLMSkillCallResult(decision=decision, activation=activation, execution=None)

        activation = MatchResult(
            skill=skill,
            confidence=decision.confidence,
            redline_pass=True,
            reason=decision.reason,
        )
        execution = SkillExecutor(self.index, adapter).execute(activation, user_query=user_query, fields=merged_fields)
        return LLMSkillCallResult(decision=decision, activation=activation, execution=execution)

    def _build_system_prompt(self) -> str:
        """构造只面向 skill 选择的系统提示。"""
        catalog = []
        for skill in self.index.list_skills():
            catalog.append(
                {
                    "name": skill.name,
                    "description": skill.description,
                    "triggers": skill.triggers,
                    "red_lines": [{"field": rule.field, "message": rule.message} for rule in skill.red_lines],
                    "references": list(skill.references),
                    "assets": [
                        {"path": asset.path, "type": asset.type, "description": asset.description}
                        for asset in skill.assets
                    ],
                }
            )

        return (
            "你是 skill 路由器。根据用户请求和 known_fields，从 skills_catalog 中选择最匹配的 skill。\n"
            "如果用户意图匹配某个 skill，即使缺少红线字段，也要选择该 skill，并把缺失字段放入 missing_fields；"
            "本地系统会负责红线拦截。\n"
            "如果没有任何 skill 适合，should_call=false 且 skill_name=null。\n"
            "只输出 JSON，不要输出 Markdown。\n"
            "JSON schema: {"
            '"should_call": boolean, "skill_name": string|null, "confidence": number, '
            '"reason": string, "fields": object, "missing_fields": string[]'
            "}。\n"
            f"skills_catalog={json.dumps(catalog, ensure_ascii=False)}"
        )

    def _parse_decision(self, raw: str, *, fallback_fields: dict[str, Any]) -> LLMSkillDecision:
        """解析大模型返回的结构化 JSON。"""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            raise LLMRouterResponseError(raw) from None
        validated = validate_llm_decision_payload(data, self.index)

        return LLMSkillDecision(
            should_call=validated["should_call"],
            skill_name=validated["skill_name"],
            confidence=validated["confidence"],
            reason=validated["reason"],
            fields={**fallback_fields, **validated["fields"]},
            missing_fields=validated["missing_fields"],
            raw_response=raw,
        )


def _check_red_lines(red_lines: tuple[RedLineRule, ...], fields: dict[str, Any]) -> list[RedLineRule]:
    """检查大模型选中 skill 后是否满足本地红线。"""
    violations: list[RedLineRule] = []
    for rule in red_lines:
        value = fields.get(rule.field)
        if value is None or value == "" or value == [] or value == {}:
            violations.append(rule)
    return violations


def _build_openai_client() -> OpenAI:
    """从 .env / 环境变量构造 OpenAI 兼容客户端。"""
    api_key = os.environ.get("API_KEY") or os.environ.get("OPENAI_API_KEY")
    base_url = os.environ.get("BASE_URL") or os.environ.get("OPENAI_BASE_URL")
    kwargs: dict[str, str] = {}
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["base_url"] = _normalize_openai_base_url(base_url)
    return OpenAI(**kwargs)


def load_skill_env() -> None:
    """显式加载当前目录或父目录中的 .env。"""
    for base in (Path.cwd(), *Path.cwd().parents):
        env_path = base / ".env"
        if env_path.is_file():
            load_dotenv(dotenv_path=env_path)
            return
    load_dotenv(dotenv_path=Path(".env"))


def _normalize_openai_base_url(base_url: str) -> str:
    """把供应商域名规整为 OpenAI-compatible API 根路径。"""
    stripped = base_url.rstrip("/")
    parsed = urlparse(stripped)
    if parsed.path in {"", "/"}:
        return f"{stripped}/v1"
    return stripped
