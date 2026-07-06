# AGENTS.md - DeepAgent Skill Mechanism

## Project overview

Reference implementation of AgentScope-style skill middleware with a two-stage pipeline (Discovery → Routing/Injection), DSL-driven via `SKILL.md` files. Skills are instructions for an agent; execution is done by agent tools, not by a prompt adapter layer.

## Key commands

```bash
# Run all tests
python3 -m pytest tests/ -v

# Run only non-LLM tests (no remote API needed)
python3 -m pytest tests/ --ignore=tests/test_skill_llm_integration.py --ignore=tests/test_skill_qa.py -v

# Test LLM skill routing from CLI
python3 scripts/llm_skill_chat.py "帮我生成一个 word 报告"

# Quick LLM connectivity test
python3 scripts/chat_with_llm.py "hello"

# Print skill index from skills/ directory
python3 -m _skill.skill
```

## Architecture

### Module separation

| 模块 | 职责 | 说明 |
|------|------|------|
| `_skill/` | **Skill 中间件**（加载 + 注入） | Discovery、解析、prompt 渲染、SkillsMiddleware |
| `core/` | **指标工具** | TokenTracker、RuntimeCollector |
| `llm/` | **LLM 路由** | OpenAIChatSkillRouter、schema 校验 |
| `agent/` | **字段抽取** | 正则提取中文自然语言中的字段 |
| `evals/` | **评测组件** | QA 质量评估、eval-only LLM answer runner |
| `tools/` | **工具层** | WordDocumentTool 等真实可执行工具 |
| `scripts/` | CLI 入口 | 测试 LLM 路由和对话 |

### Pipeline（两步）

```
用户输入 → Skill 中间件 (_skill/) 注入 name + description → LLM 路由 (llm/) 选 skill
                                                               ↓
                                              agent 读取完整 SKILL.md 并调用工具
```

### Key source directories

| Directory | Purpose |
|-----------|---------|
| `_skill/` | Skill 中间件：discovery, parser, middleware, prompt, models, utils |
| `core/` | 指标工具：TokenTracker, RuntimeCollector |
| `llm/` | LLM-based skill routing (`OpenAIChatSkillRouter`) |
| `evals/` | QA quality evaluator and eval-only `EvalLLMAnswerRunner` |
| `tools/` | Real tools, including `WordDocumentTool` |
| `tests/fakes/` | Test-only fakes |
| `agent/` | Regex-based field extraction from Chinese text |
| `scripts/` | CLI entry points for testing LLM routing and chat |
| `skills/` | 21 skill definitions in SKILL.md format (docx, pdf, cloudflare, notion, figma, etc.) |
| `tests/` | 84 non-LLM tests plus LLM routing/QA tests; `skill_fixtures.py` generates test skills |
| `docs/` | `DESIGN.md`, `TEST_DIMENSIONS.md`, `TEST_GAP_PLAN.md`, `Sills格式要求.docx` |

### Data models (all in `_skill/models.py`)

`SkillDefinition` (skill metadata), `SkillIndex` (full index produced by Discovery), `TokenMetrics`, `ExecutionMetrics`, `ExecutionContext`, `ExecutionResult`. `Execution*` models are retained for eval/reporting payloads; there is no production `SkillAdapter` protocol.

### SKILL.md DSL (official format)

Each skill is a directory with a `SKILL.md` file containing YAML frontmatter (`name`, `description`, `allowed-tools`) followed by Markdown body (`## 使用流程`, `references/`, `scripts/` 等)。见 `docs/Sills格式要求.docx` 完整规范。

## Environment & dependencies

- **Python 3.10+** (no `pyproject.toml` or `requirements.txt` — deps are installed ad-hoc)
- Required packages: `openai`, `pyyaml`, `python-dotenv`, `pytest`, `python-docx`
- `.env` at repo root provides `API_KEY`, `BASE_URL`, `MODEL` for LLM routing (uses DeepSeek API currently)
- **Do NOT commit `.env`** — it contains real API keys

## Testing notes

- Tests use `pytest` with `tmp_path` fixture; no external services needed for non-LLM tests
- LLM integration tests auto-skip if `API_KEY` is absent or provider returns rate-limit/401/403 errors
- `tests/skill_fixtures.py::build_pipeline_test_skills` creates 4 test skills aligned with the official SKILL.md format (document-generator, code-reviewer, simple-echo, data-analyzer) — the canonical test fixture for pipeline tests
- `tests/skill_fixtures.py::build_llm_test_skills` copies a subset of real skills from `skills/` for LLM routing tests
- Latest non-LLM suite: 84 passed. LLM QA is a quality gate and may fail when real model output is below threshold.

### Test file map

| File | Count | Type |
|------|-------|------|
| `test_skill_discovery.py` | 8 | Local: discovery, parsing, validation, multi-source |
| `test_skill_boundary.py` | 7 | Local: edge cases, empty dirs, long descriptions, bad YAML |
| `test_skill_field_extraction.py` | 9 | Local + LLM: regex extraction, LLM vs regex comparison |
| `test_skill_llm_integration.py` | 13 | LLM: TP/TN/field extraction/schema validation |
| `test_qa_quality_eval.py` | 7 | Local: QA evaluator and judge normalization |
| `test_word_document_tool.py` | 3 | Local: WordDocumentTool artifact generation |

## Important conventions

- Skill names must be lowercase, match `[a-z0-9][a-z0-9-]*`, max 64 chars, no leading/trailing/double hyphens
- `_skill/` uses absolute imports from itself (`from _skill.models import ...`) — this works when running from repo root with `python3 -m` or `pytest`
- The `_skill/skill.py` gate file handles import path bootstrapping for both `__package__` states
- No `.gitignore` exists — be careful not to commit `.env`, `__pycache__/`, `.pytest_cache/`, or generated docx files
