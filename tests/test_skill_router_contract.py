"""LLM 路由协议契约测试，不调用真实大模型。"""

from __future__ import annotations

from pathlib import Path
import json

import pytest

from _skill import FileSkillDiscovery
from llm.schema import LLMDecisionSchemaError
from llm.skill_router import LLMRouterResponseError, OpenAIChatSkillRouter
from tests.skill_fixtures import build_pipeline_test_skills


class _Message:
    def __init__(self, content: str):
        self.content = content


class _Choice:
    def __init__(self, content: str):
        self.message = _Message(content)


class _Response:
    def __init__(self, content: str, usage=None):
        self.choices = [_Choice(content)]
        self.usage = usage


class _FakeCompletions:
    def __init__(self, content: str, usage=None):
        self.content = content
        self.usage = usage
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _Response(self.content, self.usage)


class _FakeChat:
    def __init__(self, completions: _FakeCompletions):
        self.completions = completions


class _FakeClient:
    def __init__(self, content: str, usage=None):
        self.completions = _FakeCompletions(content, usage)
        self.chat = _FakeChat(self.completions)


def _index(tmp_path: Path):
    return FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()


def _router(tmp_path: Path, payload: dict | str) -> OpenAIChatSkillRouter:
    content = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return OpenAIChatSkillRouter(_index(tmp_path), model="fake-model", client=_FakeClient(content))


class _Usage:
    prompt_tokens = 19
    completion_tokens = 6
    total_tokens = 25


def test_router_accepts_valid_skill_decision(tmp_path: Path) -> None:
    """合法 JSON 决策应返回标准化路由结果。"""
    router = _router(
        tmp_path,
        {
            "should_call": True,
            "skill_name": "document-generator",
            "confidence": 0.9,
            "reason": "文档生成",
            "fields": {"title": "周报"},
        },
    )
    decision = router.route("生成 weekly.docx 的报告")

    assert decision.should_call is True
    assert decision.skill_name == "document-generator"
    assert decision.fields["filename"] == "weekly.docx"
    assert decision.fields["title"] == "周报"


def test_router_accepts_valid_rejection(tmp_path: Path) -> None:
    """should_call=false 时只返回拒绝决策，不进入工具或 runner。"""
    router = _router(
        tmp_path,
        {
            "should_call": False,
            "skill_name": None,
            "confidence": 0.2,
            "reason": "无匹配 skill",
            "fields": {},
        },
    )

    decision = router.route("今天北京天气怎么样")

    assert decision.should_call is False
    assert decision.skill_name is None


@pytest.mark.parametrize(
    "payload",
    [
        {"should_call": True, "skill_name": "not-exists", "confidence": 0.9, "reason": "", "fields": {}},
        {"should_call": "yes", "skill_name": None, "confidence": 0.1, "reason": "", "fields": {}},
        {"should_call": True, "skill_name": "simple-echo", "confidence": "high", "reason": "", "fields": {}},
        {"should_call": True, "skill_name": "simple-echo", "confidence": 0.8, "reason": "", "fields": []},
        {},
        {"skill_name": "simple-echo", "confidence": 0.8, "reason": "", "fields": {}},
        {"should_call": True, "skill_name": None, "confidence": 0.8, "reason": "", "fields": {}},
        {"should_call": True, "skill_name": 123, "confidence": 0.8, "reason": "", "fields": {}},
        {"should_call": False, "skill_name": [], "confidence": 0.8, "reason": "", "fields": {}},
        {"should_call": False, "skill_name": None, "confidence": None, "reason": "", "fields": {}},
        {"should_call": False, "skill_name": None, "confidence": 0.8, "reason": "", "fields": "bad"},
        [],
    ],
)
def test_router_rejects_invalid_decision_schema(tmp_path: Path, payload: dict) -> None:
    """schema 层应拒绝幻觉 skill 和类型错误。"""
    with pytest.raises(LLMDecisionSchemaError):
        _router(tmp_path, payload).route("echo ping")


def test_router_rejects_non_json_response(tmp_path: Path) -> None:
    """非 JSON 响应应抛出专门异常，方便上层统计供应商质量。"""
    with pytest.raises(LLMRouterResponseError):
        _router(tmp_path, "not json").route("echo ping")


def test_router_clamps_confidence_to_valid_range(tmp_path: Path) -> None:
    """confidence 超界时应规整到 0~1。"""
    decision = _router(
        tmp_path,
        {
            "should_call": True,
            "skill_name": "simple-echo",
            "confidence": 9,
            "reason": "",
            "fields": {},
        },
    ).route("echo ping")

    assert decision.confidence == 1.0


def test_router_clamps_negative_confidence_to_zero(tmp_path: Path) -> None:
    """confidence 低于 0 时应规整到 0。"""
    decision = _router(
        tmp_path,
        {
            "should_call": False,
            "skill_name": None,
            "confidence": -3,
            "reason": "",
            "fields": {},
        },
    ).route("天气")

    assert decision.confidence == 0.0


def test_router_stringifies_non_string_reason(tmp_path: Path) -> None:
    """reason 非字符串时应规整为字符串。"""
    decision = _router(
        tmp_path,
        {
            "should_call": False,
            "skill_name": None,
            "confidence": 0.1,
            "reason": 123,
            "fields": {},
        },
    ).route("天气")

    assert decision.reason == "123"


def test_router_exposes_actual_token_usage(tmp_path: Path) -> None:
    """路由调用返回 usage 时，应能转为真实 token 指标。"""
    payload = {
        "should_call": True,
        "skill_name": "simple-echo",
        "confidence": 0.8,
        "reason": "回显",
        "fields": {},
    }
    content = json.dumps(payload, ensure_ascii=False)
    router = OpenAIChatSkillRouter(
        _index(tmp_path),
        model="fake-model",
        client=_FakeClient(content, usage=_Usage()),
    )

    router.route("echo ping")
    metrics = router.last_token_metrics()

    assert metrics is not None
    assert metrics.input_tokens == 19
    assert metrics.output_tokens == 6
    assert metrics.total_tokens == 25
    assert metrics.source == "actual"
