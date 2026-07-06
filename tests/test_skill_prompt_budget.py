"""渐进披露 prompt 成本测试。"""

from __future__ import annotations

from pathlib import Path

from _skill import FileSkillDiscovery, SkillsMiddleware
from core.token_tracker import TokenTracker
from llm.skill_router import OpenAIChatSkillRouter
from tests.skill_fixtures import build_pipeline_test_skills


class _FakeCompletions:
    def create(self, **_kwargs):
        raise AssertionError("本测试只构建 prompt，不应调用 LLM")


class _FakeChat:
    completions = _FakeCompletions()


class _FakeClient:
    chat = _FakeChat()


def test_router_prompt_uses_lightweight_catalog_only(tmp_path: Path) -> None:
    """LLM 路由 prompt 只暴露 name + description，不注入完整 body。"""
    index = FileSkillDiscovery(build_pipeline_test_skills(tmp_path)).discover()
    router = OpenAIChatSkillRouter(index, model="fake-model", client=_FakeClient())

    prompt = router._build_system_prompt()

    assert "skills_catalog=" in prompt
    assert "document-generator" in prompt
    assert "生成 Word 文档报告" in prompt
    assert "# Document Generator" not in prompt
    assert "读取 assets/report-template.docx" not in prompt


def test_router_prompt_is_smaller_than_full_skill_bodies(tmp_path: Path) -> None:
    """对真实 skills，轻量目录 token 应明显小于完整 body 总量。"""
    repo_root = Path(__file__).resolve().parents[1]
    index = FileSkillDiscovery(repo_root / "skills").discover()
    router = OpenAIChatSkillRouter(index, model="fake-model", client=_FakeClient())
    tracker = TokenTracker()

    route_tokens = tracker.count(router._build_system_prompt())
    full_body_tokens = sum(tracker.count(skill.body) for skill in index.list_skills())

    assert route_tokens > 0
    assert full_body_tokens > 0
    assert route_tokens < full_body_tokens


def test_middleware_prompt_exposes_sources_and_load_warnings(tmp_path: Path) -> None:
    """通用中间件 prompt 应暴露来源、路径和加载告警，便于诊断。"""
    good_dir = build_pipeline_test_skills(tmp_path)
    missing_dir = tmp_path / "missing-skills"
    middleware = SkillsMiddleware([(missing_dir, "missing"), (good_dir, "fixture")])
    state: dict = {}

    middleware.before_agent(state)
    prompt = middleware.modify_system_prompt("system", state)

    assert "## Skills 系统" in prompt
    assert "**missing**" in prompt
    assert "**fixture**" in prompt
    assert "<skill_load_warnings>" in prompt
    assert "skill 来源目录不存在" in prompt
    assert "完整指令:" in prompt


def test_middleware_prompt_escapes_load_warning_content(tmp_path: Path) -> None:
    """加载告警应 JSON + HTML 转义，避免把诊断信息变成指令。"""
    missing_dir = tmp_path / "<script>alert(1)</script>"
    middleware = SkillsMiddleware([(missing_dir, "unsafe")])
    state: dict = {}

    middleware.before_agent(state)
    prompt = middleware.modify_system_prompt("system", state)

    assert "<skill_load_warnings>" in prompt
    assert "&quot;" in prompt
    assert "<script>" not in prompt


def test_middleware_respects_system_prompt_disabled(tmp_path: Path) -> None:
    """关闭 system_prompt_enabled 时不应修改系统提示。"""
    middleware = SkillsMiddleware(build_pipeline_test_skills(tmp_path), system_prompt_enabled=False)
    state: dict = {}
    middleware.before_agent(state)

    assert middleware.modify_system_prompt("base prompt", state) == "base prompt"


def test_multi_source_prompt_marks_last_source_as_higher_priority(tmp_path: Path) -> None:
    """多个 source 展示时最后一个来源应标记更高优先级。"""
    source_a = build_pipeline_test_skills(tmp_path / "a")
    source_b = build_pipeline_test_skills(tmp_path / "b")
    middleware = SkillsMiddleware([(source_a, "base"), (source_b, "override")])
    state: dict = {}

    middleware.before_agent(state)
    prompt = middleware.modify_system_prompt("system", state)

    assert "**base**" in prompt
    assert "**override**" in prompt
    assert "**override**" in prompt and "（更高优先级）" in prompt


def test_router_prompt_stays_under_expected_token_budget() -> None:
    """当前 21 个真实 skill 的路由 prompt 应处在可控 token 范围内。"""
    repo_root = Path(__file__).resolve().parents[1]
    index = FileSkillDiscovery(repo_root / "skills").discover()
    router = OpenAIChatSkillRouter(index, model="fake-model", client=_FakeClient())
    tokens = TokenTracker().count(router._build_system_prompt())

    assert tokens < 3000


def test_router_prompt_contains_each_skill_once() -> None:
    """真实 skill 清单中每个 name 应在路由 prompt 至少出现一次。"""
    repo_root = Path(__file__).resolve().parents[1]
    index = FileSkillDiscovery(repo_root / "skills").discover()
    prompt = OpenAIChatSkillRouter(index, model="fake-model", client=_FakeClient())._build_system_prompt()

    for skill in index.list_skills():
        assert f'"name": "{skill.name}"' in prompt


def test_router_prompt_handles_empty_skill_index(tmp_path: Path) -> None:
    """空 skill 目录也应生成合法路由 prompt。"""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    index = FileSkillDiscovery(empty_dir).discover()
    prompt = OpenAIChatSkillRouter(index, model="fake-model", client=_FakeClient())._build_system_prompt()

    assert "skills_catalog=[]" in prompt


def test_load_warnings_are_truncated(tmp_path: Path) -> None:
    """过长加载告警应被截断，避免诊断内容污染 prompt。"""
    from _skill.prompt import format_skills_prompt

    long_warning = "x" * 5000
    prompt = format_skills_prompt([], load_errors=(long_warning,))

    assert len(prompt) < 2000
    assert "已截断" in prompt
