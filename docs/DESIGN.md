# DeepAgent Skill 系统设计文档

> 对标官方 Skill 格式规范（`docs/Sills格式要求.docx`） | 加载 + 注入 + LLM 路由 + 执行 + 量化评估

## 1. 架构概览

```
┌─────────────────────────────────────┐
│           _skill/ Skill 中间件        │
│  扫描/解析 SKILL.md → 注入 prompt      │
│  (Discovery + Prompt Injection)      │
└──────────────┬──────────────────────┘
               │ skills_catalog {name, description}
               ▼
┌─────────────────────────────────────┐
│           llm/ 大模型路由             │
│  LLM 选 skill → JSON schema 校验      │
│  (OpenAIChatSkillRouter)             │
└──────────────┬──────────────────────┘
               │ selected skill
               ▼
┌─────────────────────────────────────┐
│           core/ 执行器                │
│  构建 prompt → 调适配器 → 记录指标     │
│  (SkillExecutor + TokenTracker)      │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│         adapters/ 框架适配器          │
│  OpenAICompatible / LangChain        │
│  SpringAI / WordDocument             │
└─────────────────────────────────────┘
```

## 2. 模块职责

| 模块 | 文件 | 职责 |
|------|------|------|
| `_skill/models.py` | SkillDefinition, SkillIndex | 数据模型 |
| `_skill/parser.py` | parse_skill_file | 解析 SKILL.md YAML frontmatter |
| `_skill/discovery.py` | FileSkillDiscovery | 扫描 skills/ 目录 → SkillIndex |
| `_skill/middleware.py` | SkillsMiddleware | before_agent + system prompt 注入 |
| `_skill/prompt.py` | format_skills_prompt | 渲染可用 skill 清单 |
| `core/executor.py` | SkillExecutor, TokenTracker | 构建 prompt + 调适配器 + 记录 token |
| `core/runtime_metrics.py` | RuntimeCollector | 混淆矩阵 + token + 延迟采集 |
| `llm/skill_router.py` | OpenAIChatSkillRouter | LLM 选择 skill |
| `llm/schema.py` | validate_llm_decision_payload | 校验 LLM 返回的 JSON |
| `adapters/skill_adapters.py` | 4 种 Adapter | 真实执行 |
| `agent/field_extractor.py` | extract_fields_from_query | 正则提取中文字段 |
| `scripts/chat_with_llm.py` | CLI | 测试 `.env` 中的大模型连通性 |
| `scripts/llm_skill_chat.py` | CLI | 真实 LLM 路由 + 本地 mock adapter 执行 |
| `evals/` | 预留 | 当前仅保留包入口，批量 evaluator 尚未接入源码 |

## 3. SKILL.md 格式

对齐官方规范（`docs/Sills格式要求.docx`），仅要求以下 YAML frontmatter 字段：

```yaml
---
name: skill-name                    # 必填：小写字母+数字+连字符，1-64 字符
description: 功能描述与触发条件      # 必填：最多 1024 字符
allowed-tools: Read, Bash, Write    # 可选：推荐使用的工具
license: MIT                        # 可选
compatibility: python>=3.10          # 可选
---

# 使用流程
1. 判断任务是否命中本 skill
2. 按需读取 references/ 中的资料
3. 调用 scripts/ 中的可执行脚本
4. 使用 assets/ 中的模板或素材
```

**不再使用的字段**（已移除）：`triggers`, `red_lines`, `references` (YAML 声明), `assets` (YAML 声明), `metrics`, `token_estimate`。

当前解析器还允许可选 `metadata` mapping，并将其规整为 `dict[str, str]`；它只作为扩展元信息保存，不参与路由、红线或执行决策。

> references/、assets/、scripts/ 以目录形式存在，由 Agent 运行时按需读取，不在 SKILL.md 中声明。

## 4. 渐进披露（Progressive Disclosure）

两步走，对齐官方格式的分层暴露策略：

**第一步 — 轻量目录**：LLM 路由时，`OpenAIChatSkillRouter` 的 system prompt 只包含 `skills_catalog=[{name, description}]`。当前仓库 `skills/` 下有 21 个 skill。

`SkillsMiddleware.modify_system_prompt()` 面向通用 Agent 注入时，会额外展示 skill 来源、完整 `SKILL.md` 路径、license/compatibility 和加载告警；这不是 LLM 路由专用 prompt。

**第二步 — 按需读取**：LLM 选中 skill 后，执行器才加载完整的 SKILL.md body（平均 11000 字符），组装为执行 prompt。

```
路由阶段: {name, description} × 21   →  LLM 选一个
执行阶段: 完整 SKILL.md body          →  适配器执行
```

## 5. 路由流程

```
用户输入: "帮我生成一份 Word 报告"
    │
    ├─ 1. extract_fields_from_query()  正则预提取 filename/template_name
    │
    ├─ 2. _build_system_prompt()       构建 skills_catalog [{name, desc}, ...]
    │
    ├─ 3. OpenAI-compatible API 调用   temperature=0, response_format=json_object
    │      返回: {should_call, skill_name, confidence, reason, fields}
    │
    ├─ 4. validate_llm_decision_payload()  校验 should_call/bool, skill_name 存在性
    │
    └─ 5. SkillExecutor.execute()      构建 prompt → 调 adapter
```

## 6. 路由准确度评估（混淆矩阵）

LLM 路由的准确性通过混淆矩阵量化，替代原来的本地关键词/红线规则校验：

| 类型 | 含义 | 示例 |
|------|------|------|
| **TP** | 期望激活某 skill，LLM 正确选中 | "生成 word 报告" → document-generator ✅ |
| **TN** | 期望不激活，LLM 正确拒绝 | "今天天气" → should_call=false ✅ |
| **FP** | 期望不激活，LLM 误激活 | "写代码" → 误选 code-reviewer |
| **FN** | 期望激活，LLM 漏激活 | "生成报告" → should_call=false |

指标计算公式：

```
Accuracy  = (TP + TN) / (TP + TN + FP + FN)
Precision = TP / (TP + FP)
Recall    = TP / (TP + FN)
```

## 7. 执行流程

```
SkillExecutor.execute(skill, user_query, fields)
    │
    ├─ _build_prompt():    组装
    │     # Skill: {name}
    │     ## Skill 描述
    │     {description}
    │     ## 用户请求
    │     {user_query}
    │     ## 结构化字段
    │     {fields}
    │     ## Skill 指令
    │     {body}
    │
    ├─ adapter.execute()   调用适配器
    │
    └─ TokenTracker       记录 input/output/total token + overhead%
```

## 8. 适配器

| 适配器 | 用途 | 调用方式 |
|--------|------|---------|
| OpenAICompatibleSkillAdapter | 将 prompt 发给 LLM 执行 | OpenAI-compatible Chat Completions API |
| LangChainSkillAdapter | 委托 LangChain Runnable | runnable.invoke(payload) |
| SpringAIHttpAdapter | HTTP POST 到 SpringAI 服务 | urllib.request |
| WordDocumentSkillAdapter | 生成 .docx 文件 | python-docx |

## 9. 量化指标体系

每次 `pytest` 运行会自动输出测试汇总到 `test-results/` 目录；当测试中使用 `runtime_collector` / `get_runtime_collector()` 记录了数据时，同时输出量化报告。

| 报告文件 | 内容 |
|----------|------|
| `test-report.json` / `.md` | 51 条测试 pass/fail/skip/error 明细 + 耗时 |
| `quantitative-report.json` / `.md` | 混淆矩阵 (TP/TN/FP/FN) + Accuracy/Precision/Recall |
| | Token 消耗 (min/max/avg/total) |
| | 延迟 (min/max/avg/p50/p95) |
| | 按 skill 分组：执行次数、平均 Token、平均延迟、成功率 |
| | 按适配器分组：同上 |
| | 逐次执行明细表 |

当前量化指标只来自测试显式记录的路由和执行样本，不是线上全量遥测。Token 由 `TokenTracker` 使用字符数近似估算，不等同于供应商 API 返回的精确 token usage。

## 10. 测试覆盖

| 文件 | 条数 | 类型 |
|------|------|------|
| `test_skill_discovery.py` | 8 | 本地：解析、校验、多源覆盖 |
| `test_skill_execution.py` | 6 | 本地：prompt 构建、token、异常兜底 |
| `test_skill_adapters.py` | 8 | 本地+LLM：4 种适配器 |
| `test_skill_boundary.py` | 7 | 本地：边界与鲁棒性 |
| `test_skill_field_extraction.py` | 9 | 本地+LLM：正则提取、LLM 对比 |
| `test_skill_llm_integration.py` | 13 | LLM：TP/TN/字段提取/schema 校验 |

## 11. 当前真实链路与 mock 边界

| 场景 | 真实部分 | mock / 兜底部分 |
|------|----------|-----------------|
| `scripts/chat_with_llm.py` | 真实 OpenAI-compatible LLM 对话 | 无 skill 路由和执行 |
| `scripts/llm_skill_chat.py` | 真实 LLM 路由、真实 `skills/` Discovery | 使用 `CallableSkillAdapter("mock-adapter")`，只返回 `called:{skill.name}` |
| `OpenAIChatSkillRouter.route()` | 真实 LLM 选择 skill + schema 校验 | 字段提取先用正则兜底，再合并 LLM fields |
| `OpenAIChatSkillRouter.route_and_execute()` | 真实路由 + 真实 `SkillExecutor` | 执行是否真实取决于传入 adapter |
| `WordDocumentSkillAdapter` | 真实生成 `.docx` 文件 | 文档内容是最小实现，不是业务模板渲染 |
| `LangChainSkillAdapter` | 真实调用传入 runnable/callable | 测试中 runnable 是本地假对象 |
| `SpringAIHttpAdapter` | 真实 HTTP POST 实现 | 当前测试只覆盖无效 endpoint 的失败路径 |
| `OpenAICompatibleSkillAdapter` | 有 API_KEY 时真实调用 LLM 执行 prompt | 无 API_KEY 或供应商不可用时测试自动 skip |

## 12. 已知待同步项

- `docs/TEST_DIMENSIONS.md` 和 `docs/TEST_GAP_PLAN.md` 仍包含旧版 `SkillActivator`、`red_lines`、多轮会话和 72 条测试描述，已不符合当前源码。
- `evals/skill_evaluator.py` 源文件已不存在，仅残留 `__pycache__`，不应作为当前能力依据。
- 当前没有本地红线拦截模块；是否需要恢复“必填字段/多轮补全”能力，需要先确认业务规则。

