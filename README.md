# Enterprise Office Agent

DeepAgent Skill 机制的参考实现。项目围绕 `SKILL.md` 文件实现 skill 的发现、解析、注入、路由和量化评估，核心目标是验证一套可测试、可观测、可扩展的 skill 中间件链路。

## 核心链路

```text
用户 Query
  -> 字段预提取 agent/field_extractor.py
  -> Skill Discovery _skill/discovery.py
  -> SKILL.md 解析 _skill/parser.py
  -> LLM 路由 llm/skill_router.py
  -> schema 校验 llm/schema.py
  -> 返回 skill_name / fields / reason
  -> 真实 agent 按需读取 SKILL.md 并调用工具
```

路由阶段只向大模型暴露 `name + description`，用于降低 prompt 成本。正式 agent 运行时应在选中某个 skill 后按需读取完整 `SKILL.md`，再调用已有工具执行。

当前仓库不再提供 `SkillExecutor + adapter` 这类绕过 agent 的 prompt 执行层。QA 问答集需要生成答案时，使用 `evals/llm_answer_runner.py` 作为评测专用 runner；真实动作能力放在 `tools/` 中。

## 目录结构

| 目录 | 说明 |
|------|------|
| `_skill/` | Skill 中间件：模型、解析、发现、prompt 注入、命令行入口 |
| `llm/` | OpenAI-compatible LLM 路由和返回 schema 校验 |
| `core/` | TokenTracker、RuntimeCollector |
| `agent/` | 中文自然语言字段预提取 |
| `skills/` | 实际 skill 定义，每个 skill 目录包含 `SKILL.md` |
| `datasets/` | 路由评测和 QA 数据集 |
| `evals/` | 路由评测、QA 质量评估、评测专用 LLM runner |
| `tools/` | 真实工具实现，例如 `WordDocumentTool` |
| `scripts/` | CLI 测试入口和报告生成脚本 |
| `tests/` | 自动化测试 |
| `tests/fakes/` | 测试专用 fake |
| `docs/` | 设计文档、测试维度、系统报告 |
| `test-results/` | pytest、路由评测、QA 评测和质量摘要输出 |

## 环境要求

- Python 3.10+
- 依赖包：`openai`、`pyyaml`、`python-dotenv`、`pytest`、`python-docx`
- 根目录 `.env` 提供真实 LLM 配置：

```env
API_KEY=your_api_key
BASE_URL=https://your-provider-compatible-base-url
MODEL=your-model-name
```

不要提交 `.env`，里面包含真实密钥。

## 常用命令

运行全部测试：

```bash
python3 -m pytest tests/ -v
```

运行不依赖远程 LLM 的主测试：

```bash
python3 -m pytest tests/ \
  --ignore=tests/test_skill_llm_integration.py \
  --ignore=tests/test_skill_qa.py \
  -v
```

测试 LLM 是否能连通：

```bash
python3 scripts/chat_with_llm.py "hello"
```

测试自然语言 skill 路由：

```bash
python3 scripts/llm_skill_chat.py "帮我生成一个 word 报告"
```

打印当前 skill 索引：

```bash
python3 -m _skill.skill
```

生成大样本路由评测报告：

```bash
python3 scripts/run_routing_eval.py --output-dir test-results
```

生成 skill 质量摘要：

```bash
python3 scripts/run_skill_quality.py --output-dir test-results
```

## 量化指标速览

以下指标来自当前 `test-results/` 下的最新报告，用于快速判断系统状态，详细分析见 `docs/SKILL_SYSTEM_TEST_REPORT_2026-07-03.md`。

| 评测项 | 样本/范围 | 最新结果 | 说明 |
|--------|-----------|----------|------|
| 大样本路由准确率 | 120 条真实 LLM 路由样本 | 90.8% | `routing-eval-report.*`，109/120 通过 |
| 大样本路由 Precision | 120 条真实 LLM 路由样本 | 90.2% | TP=74, FP=8 |
| 大样本路由 Recall | 120 条真实 LLM 路由样本 | 96.1% | TP=74, FN=3 |
| QA 路由准确率 | 20 条 Render QA 样本 | 90.0% | TP=17, TN=1, FP=1, FN=1 |
| QA 综合评分 | 20 条 Render QA 样本 | 76.0% | 加权包含路由、要素、本地质量、judge、语言、严重错误 |
| QA 关键要素命中 | 20 条 Render QA 样本 | 69.6% | 检查必须出现的技术要点 |
| QA 本地确定性质量 | 20 条 Render QA 样本 | 71.0% | 检查步骤顺序、配置、文档标准、禁用项等 |
| QA LLM Judge 语义质量 | 20 条 Render QA 样本 | 64.8% | 判断技术正确性、问题解决度、隐蔽严重错误 |
| QA 幻觉控制 | 20 条 Render QA 样本 | 100.0% | 未发现不存在的 `scripts/`、`references/`、`assets/` 引用 |
| QA 严重错误控制 | 20 条 Render QA 样本 | 85.0% | 仍有 1 条严重问题样本 |
| QA 答案生成成功率 | 17 次真实 QA runner 调用 | 100.0% | `EvalLLMAnswerRunner` 调用均成功 |
| QA 路由 token | 20 次真实路由 | 平均 2102.8，总计 42056 | 来源为供应商 actual usage |
| QA 执行 token | 17 次真实执行 | 平均 5129.1，总计 87194 | 来源为供应商 actual usage |
| Skill 加载 | 21 个 skill | 0 加载错误 | `skill-quality-summary.*` |
| Prompt 成本 | 21 个 skill | 路由 prompt 2046 token | 只注入 `name + description` |
| 全量注入成本 | 21 个 skill | 约 60571 token | 若把所有 body 塞入 prompt 的估算成本 |
| 渐进披露节省率 | 21 个 skill | 96.6% | 相比全量注入 |
| 字段抽取质量 | 50 条字段样本 | Precision/Recall 100% | 当前明确字段表达样本 |

当前结论：路由链路整体可用，skill 加载和 token 统计稳定；主要短板在 QA 输出质量，尤其是答案是否直接给出可执行方案、复杂配置是否真实可靠、相近部署 skill 的边界判断。

## SKILL.md 格式

每个 skill 是一个目录，目录下必须包含 `SKILL.md`。

```yaml
---
name: docx-report-generator
description: 生成 Word 文档报告，根据指定模板填充内容并输出 docx 文件。
allowed-tools: Read, Bash, Write
license: MIT
compatibility: python>=3.10
---

# 使用流程
1. 判断用户是否需要生成 Word 报告
2. 确认文件名、标题、模板等字段
3. 按 SKILL.md 正文中的流程执行
```

必填字段：

- `name`：小写字母、数字和连字符，最长 64 字符
- `description`：用于路由阶段判断是否命中，最长 1024 字符

可选字段：

- `allowed-tools`
- `license`
- `compatibility`
- `metadata`

## Agent 执行口径

正式链路中，skill 本身只是说明书，不直接执行。Agent 在 system prompt 中看到 skill 列表，决定命中某个 skill 后，再读取完整 `SKILL.md`，按说明调用已有工具，例如 Bash、Write、Read、MCP 或 `tools/` 中的工具。

```text
用户请求
  -> Agent 读取 skill 列表
  -> Agent 决定使用某个 skill
  -> Agent 读取完整 SKILL.md
  -> Agent 按说明调用工具
```

QA 自动化测试为了评估“路由后答案是否可靠”，会使用 `evals/llm_answer_runner.py` 生成评测答案。它是 eval-only runner，不是生产 agent 架构的一部分。

真实可执行能力应放在 `tools/`。当前已有 `tools/word_document_tool.py::WordDocumentTool`，用于通过 `python-docx` 生成 `.docx` 文件。

## 测试报告

测试和脚本会在 `test-results/` 下输出报告：

| 文件 | 内容 |
|------|------|
| `test-report.md/json` | pytest 通过率、失败、跳过和耗时 |
| `quantitative-report.md/json` | pytest 运行时记录的混淆矩阵、token、延迟、执行成功率 |
| `routing-eval-report.md/json` | 大样本 LLM 路由评测 |
| `qa-report.md/json` | QA 问答集评测结果 |
| `skill-quality-summary.md/json` | skill 库存、prompt 成本、字段抽取质量 |

## 重要文档

- [docs/DESIGN.md](docs/DESIGN.md)：系统设计
- [docs/TEST_DIMENSIONS.md](docs/TEST_DIMENSIONS.md)：测试维度
- [docs/SKILL_MIDDLEWARE_PIPELINE_REPORT_2026-07-03.md](docs/SKILL_MIDDLEWARE_PIPELINE_REPORT_2026-07-03.md)：skill 中间件链路报告
- [docs/SKILL_SYSTEM_TEST_REPORT_2026-07-03.md](docs/SKILL_SYSTEM_TEST_REPORT_2026-07-03.md)：系统测试汇报
