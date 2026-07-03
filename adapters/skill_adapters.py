"""Skill 执行适配器。"""

from __future__ import annotations

from typing import Any
import json
import urllib.error
import urllib.request

from openai import OpenAI

from _skill.models import SkillDefinition
from llm.skill_router import _build_openai_client, load_skill_env


class OpenAICompatibleSkillAdapter:
    """把已组装的 skill prompt 交给 OpenAI-compatible chat API 执行。"""

    name = "OpenAICompatible"

    def __init__(self, *, model: str | None = None, client: OpenAI | None = None) -> None:
        load_skill_env()
        import os

        self.model = model or os.environ.get("MODEL") or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        self.client = client or _build_openai_client()
        self.last_token_usage: Any = None

    def execute(self, prompt: str, *, skill: SkillDefinition, context: dict[str, Any]) -> str:
        """调用大模型执行 skill prompt。"""
        self.last_token_usage = None
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0.2,
            messages=[
                {"role": "system", "content": f"你正在执行 skill: {skill.name}。请严格遵循上下文。"},
                {"role": "user", "content": prompt},
            ],
        )
        self.last_token_usage = getattr(response, "usage", None)
        return response.choices[0].message.content or ""


class LangChainSkillAdapter:
    """包装 LangChain Runnable / Chain，适配 SkillAdapter 协议。"""

    name = "LangChain"

    def __init__(self, runnable: Any) -> None:
        self.runnable = runnable
        self.last_token_usage: Any = None

    def execute(self, prompt: str, *, skill: SkillDefinition, context: dict[str, Any]) -> Any:
        """调用 LangChain 的 invoke 接口。"""
        self.last_token_usage = None
        payload = {"input": prompt, "skill": skill.name, "context": context}
        if hasattr(self.runnable, "invoke"):
            try:
                result = self.runnable.invoke(payload)
            except TypeError:
                result = self.runnable.invoke(prompt)
            self.last_token_usage = _extract_usage(result)
            return result
        if callable(self.runnable):
            result = self.runnable(prompt)
            self.last_token_usage = _extract_usage(result)
            return result
        raise TypeError("LangChainSkillAdapter 需要 runnable.invoke 或 callable")


class SpringAIHttpAdapter:
    """通过 HTTP 调用 SpringAI 服务。"""

    name = "SpringAI"

    def __init__(self, endpoint: str, *, timeout: float = 30.0) -> None:
        self.endpoint = endpoint
        self.timeout = timeout
        self.last_token_usage: Any = None

    def execute(self, prompt: str, *, skill: SkillDefinition, context: dict[str, Any]) -> Any:
        """向 SpringAI HTTP endpoint POST prompt 和上下文。"""
        self.last_token_usage = None
        body = json.dumps(
            {"prompt": prompt, "skill": skill.name, "context": context},
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"SpringAI HTTP {exc.code}: {raw}") from exc
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            return raw
        self.last_token_usage = _extract_usage(result)
        return result


def _extract_usage(value: Any) -> Any:
    """从常见 LLM 返回对象中提取 usage，供执行器统计真实 token。"""
    if value is None:
        return None
    if isinstance(value, dict):
        usage = value.get("usage")
        if usage is not None:
            return usage
        llm_output = value.get("llm_output")
        if isinstance(llm_output, dict):
            return llm_output.get("token_usage") or llm_output.get("usage")
        response_metadata = value.get("response_metadata")
        if isinstance(response_metadata, dict):
            return response_metadata.get("token_usage") or response_metadata.get("usage")
        return None

    usage = getattr(value, "usage", None)
    if usage is not None:
        return usage

    response_metadata = getattr(value, "response_metadata", None)
    if isinstance(response_metadata, dict):
        return response_metadata.get("token_usage") or response_metadata.get("usage")

    llm_output = getattr(value, "llm_output", None)
    if isinstance(llm_output, dict):
        return llm_output.get("token_usage") or llm_output.get("usage")

    return None
