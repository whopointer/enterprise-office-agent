# DeepAgent Skill 系统设计文档

> 对标官方 Skill 格式规范（`docs/Sills格式要求.docx`） | 加载 + 注入 + LLM 路由 + 工具执行边界 + 量化评估

## 1. 架构概览

```text
┌─────────────────────────────────────┐
│           _skill/ Skill 中间件        │
│  扫描/解析 SKILL.md → 注入 prompt      │
│  Discovery + Parser + Middleware     │
└──────────────┬──────────────────────┘
               │ skills_catalog {name, description}
               ▼
┌─────────────────────────────────────┐
│           llm/ 大模型路由             │
│  LLM 选 skill → JSON schema 校验      │
│  OpenAIChatSkillRouter.route()       │
└──────────────┬──────────────────────┘
               │ decision {skill_name, fields, reason}
               ▼
┌─────────────────────────────────────┐
│              Agent Runtime           │
│  读取完整 SKILL.md → 自行调用工具       │
│  Bash / Write / Read / MCP / tools    │
└─────────────────────────────────────┘
```

本仓库不再提供 `SkillExecutor + adapters` 作为正式执行层。Skill 本身是说明书，执行应由 agent runtime 根据 `SKILL.md` 调用工具完成。

QA 自动化评测需要生成答案时，使用 `evals/llm_answer_runner.py`。它是 eval-only runner，不是生产 agent 架构。

## 2. 模块职责

| 模块 | 文件 | 职责 |
|------|------|------|
| `_skill/models.py` | SkillDefinition, SkillIndex | Skill 数据模型 |
| `_skill/parser.py` | parse_skill_file | 解析 SKILL.md YAML frontmatter |
| `_skill/discovery.py` | FileSkillDiscovery | 扫描 skills/ 目录 → SkillIndex |
| `_skill/middleware.py` | SkillsMiddleware | before-agent system prompt 注入 |
| `_skill/prompt.py` | format_skills_prompt | 渲染可用 skill 清单 |
| `llm/skill_router.py` | OpenAIChatSkillRouter | LLM 选择 skill，仅负责路由 |
| `llm/schema.py` | validate_llm_decision_payload | 校验 LLM 返回 JSON |
| `core/token_tracker.py` | TokenTracker | actual usage 读取与估算 fallback |
| `core/runtime_metrics.py` | RuntimeCollector | 混淆矩阵 + token + 延迟采集 |
| `evals/qa_quality.py` | evaluate_answer_locally | QA 本地确定性质量检查 |
| `evals/llm_answer_runner.py` | EvalLLMAnswerRunner | QA 评测专用答案生成 runner |
| `tools/word_document_tool.py` | WordDocumentTool | 真实 docx 生成工具 |
| `agent/field_extractor.py` | extract_fields_from_query | 正则提取中文字段 |
| `scripts/chat_with_llm.py` | CLI | 测试 `.env` 中的大模型连通性 |
| `scripts/llm_skill_chat.py` | CLI | 真实 LLM skill 路由测试 |

## 3. SKILL.md 格式

对齐官方规范（`docs/Sills格式要求.docx`），仅要求以下 YAML frontmatter 字段：

```yaml
---
name: skill-name
description: 功能描述与触发条件
allowed-tools: Read, Bash, Write
license: MIT
compatibility: python>=3.10
---

# 使用流程
1. 判断任务是否命中本 skill
2. 按需读取 references/ 中的资料
3. 调用 scripts/ 中的可执行脚本
4. 使用 assets/ 中的模板或素材
```

不再使用的字段：`triggers`, `red_lines`, `references` YAML 声明, `assets` YAML 声明, `metrics`, `token_estimate`。

`references/`、`assets/`、`scripts/` 以目录形式存在，由 Agent 运行时按需读取，不在 SKILL.md 中声明。

## 4. 渐进披露

两步走，对齐官方格式的分层暴露策略：

1. 路由阶段只注入 `name + description`，控制 prompt 成本。
2. Agent 决定使用某个 skill 后，再读取完整 `SKILL.md` body 和相关资源。

```text
路由阶段: {name, description} × 21
执行阶段: agent 按需读取完整 SKILL.md / references / scripts / assets
```

`SkillsMiddleware.modify_system_prompt()` 面向通用 Agent 注入，会展示 skill 来源、路径、license/compatibility 和加载告警。`OpenAIChatSkillRouter` 面向评测，只构造轻量 `skills_catalog`。

## 5. 路由流程

```text
用户输入: "帮我生成一份 Word 报告"
    │
    ├─ 1. extract_fields_from_query()  正则预提取 filename/template_name
    │
    ├─ 2. _build_system_prompt()       构建 skills_catalog [{name, desc}, ...]
    │
    ├─ 3. OpenAI-compatible API 调用   temperature=0, response_format=json_object
    │      返回: {should_call, skill_name, confidence, reason, fields}
    │
    └─ 4. validate_llm_decision_payload()  校验 should_call/bool, skill_name 存在性
```

`OpenAIChatSkillRouter.route()` 只返回路由决策，不执行 skill。

## 6. Agent 执行边界

正式 agent 框架中的执行流程应是：

```text
用户输入
  -> agent 看到 system prompt 中的 skill 列表
  -> agent 决定使用某个 skill
  -> agent 读取完整 SKILL.md
  -> agent 按 SKILL.md 调用已有工具
```

本仓库已删除旧的 `SkillExecutor + adapters` 执行链路，避免把 eval runner 误当成生产架构。

## 7. QA 评测执行边界

QA 问答集为了评估“路由后答案是否可靠”，需要一个可重复的答案生成方式。该能力位于：

```text
evals/llm_answer_runner.py
```

职责：

- 根据 `skill + user_query + fields` 生成 QA 评测 prompt。
- 调用 OpenAI-compatible Chat Completions。
- 读取供应商 actual usage。
- 返回 output、prompt 和 `ExecutionMetrics`。

它只服务自动化评测，不参与正式 agent 执行链路。

## 8. 工具层

真实可执行动作放入 `tools/`。

| 工具 | 用途 |
|------|------|
| `WordDocumentTool` | 基于 `python-docx` 生成 `.docx` 文件 |

后续如果需要 Bash、文件写入、MCP、HTTP 等能力，应以 tool 形式挂给 agent runtime，而不是恢复 `adapter.execute(prompt)`。

## 9. 路由准确度评估

LLM 路由通过混淆矩阵量化：

| 类型 | 含义 | 示例 |
|------|------|------|
| TP | 期望激活某 skill，LLM 正确选中 | "生成 word 报告" → document-generator |
| TN | 期望不激活，LLM 正确拒绝 | "今天天气" → should_call=false |
| FP | 期望不激活，LLM 误激活 | "写代码" → 误选 code-reviewer |
| FN | 期望激活，LLM 漏激活 | "生成报告" → should_call=false |

```text
Accuracy  = (TP + TN) / (TP + TN + FP + FN)
Precision = TP / (TP + FP)
Recall    = TP / (TP + FN)
```

## 10. QA 答案质量评估

QA 不做标准答案全文比对，而是组合判断：

| 维度 | 判定方式 |
|------|----------|
| 技术正确性 | `technical_checks` + LLM judge |
| 步骤顺序 | `ordered_steps` + LLM judge |
| 配置可执行性 | `config_checks` 解析配置块 |
| 文档标准 | `document_standard` |
| 问题解决度 | LLM judge `problem_resolution` |
| 隐蔽严重错误 | `forbidden` + judge `hidden_critical_errors` |
| 幻觉引用 | 检查 `scripts/`、`references/`、`assets/` 路径是否存在 |

## 11. 量化报告

每次 pytest 运行会自动输出：

| 报告文件 | 内容 |
|----------|------|
| `test-report.json/md` | pytest pass/fail/skip/error 明细 |
| `quantitative-report.json/md` | pytest 运行时路由、token、延迟、执行成功率 |
| `routing-eval-report.json/md` | 120 条真实 LLM 大样本路由评测 |
| `qa-report.json/md` | QA 问答集质量评测 |
| `skill-quality-summary.json/md` | skill 盘点、prompt 预算、字段抽取质量 |

Token 优先使用供应商 API 返回的真实 usage；拿不到 usage 时，`TokenTracker` 回退到字符数近似估算。

## 12. 测试覆盖

当前非 LLM 测试覆盖：

| 文件 | 类型 |
|------|------|
| `test_skill_discovery.py` | SKILL.md 解析、校验、多源覆盖 |
| `test_skill_boundary.py` | 边界与鲁棒性 |
| `test_skill_field_extraction.py` | 字段提取 |
| `test_skill_prompt_budget.py` | prompt 成本与渐进披露 |
| `test_skill_router_contract.py` | 路由 schema 契约 |
| `test_qa_quality_eval.py` | QA 本地质量评估 |
| `test_runtime_metrics_report.py` | 量化报告 |
| `test_word_document_tool.py` | Word 工具 |

LLM 相关测试：

| 文件 | 类型 |
|------|------|
| `test_skill_llm_integration.py` | 真实 LLM 路由 TP/TN/schema |
| `test_skill_qa.py` | 真实 LLM QA 答案质量评测 |

## 13. 当前真实链路与评测边界

| 场景 | 真实部分 | 评测/兜底部分 |
|------|----------|---------------|
| `scripts/chat_with_llm.py` | 真实 OpenAI-compatible LLM 对话 | 无 skill 路由 |
| `scripts/llm_skill_chat.py` | 真实 LLM 路由、真实 `skills/` Discovery | 不执行 skill |
| `OpenAIChatSkillRouter.route()` | 真实 LLM 选择 skill + schema 校验 | 字段提取先用正则兜底 |
| `EvalLLMAnswerRunner` | 真实 LLM 生成 QA 答案 | eval-only，不是生产执行层 |
| `WordDocumentTool` | 真实生成 `.docx` 文件 | 当前是最小实现，不是业务模板渲染 |

## 14. 后续方向

- 接入真实 agent runtime，让 agent 自己读取 SKILL.md 并调用工具。
- 增强 `tools/`，把可执行能力明确注册为工具。
- 继续扩展 QA 数据集到更多 skill，而不是只覆盖 Render deploy。
- 强化复杂配置校验，减少 LLM judge 才能发现的问题。
