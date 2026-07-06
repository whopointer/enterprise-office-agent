# Skill 系统测试维度文档

> 最后更新: 2026-07-06 | 当前非 LLM 主测试: 84 passed | 架构口径: 中间件加载注入 + LLM 路由，agent/tool 执行

## 1. 测试架构

```text
用户 Query
  -> agent/field_extractor.py         字段预提取
  -> _skill/discovery.py              扫描 skills/*/SKILL.md
  -> _skill/parser.py                 解析 frontmatter + body
  -> _skill/prompt.py                 生成 name + description 清单
  -> llm/skill_router.py              LLM 路由
  -> llm/schema.py                    本地 schema 校验
  -> 返回 should_call / skill_name / fields / reason
  -> agent runtime 按需读取完整 SKILL.md 并调用工具
```

正式链路不再包含 `SkillExecutor + adapters`。这些模块会绕过 agent，直接把 prompt 发给另一个执行端，不符合“skill 是说明书，agent 自己决定并调用工具”的设计口径。

QA 问答集为了测试“选中 skill 后答案是否可靠”，使用 `evals/llm_answer_runner.py` 生成评测答案。它是 eval-only runner，不是生产 agent runtime。

## 2. 测试维度全景

### 维度 A - Skill 加载与解析

| 目标 | 覆盖点 | 主要文件 |
|------|--------|----------|
| 正确读取 skill | 解析 `name`、`description`、`allowed-tools`、正文、license | `tests/test_skill_discovery.py` |
| 忽略非 skill 文件 | 非 skill 目录不进入索引 | `tests/test_skill_discovery.py` |
| 多来源覆盖 | 同名 skill 高优先级覆盖低优先级 | `tests/test_skill_discovery.py` |
| 解析失败隔离 | 坏 `SKILL.md` 进入 `load_errors`，不影响其他 skill | `tests/test_skill_discovery.py`、`tests/test_skill_boundary.py` |
| 格式校验 | 非法 skill 名、缺失 description、非法 YAML | `tests/test_skill_boundary.py` |

量化数据：加载成功数、加载错误数、description 截断、超大正文兼容性。

### 维度 B - Prompt 注入与 Token 成本

| 目标 | 覆盖点 | 主要文件 |
|------|--------|----------|
| 轻量注入 | system prompt 只暴露 `name + description` | `tests/test_skill_prompt_budget.py` |
| 加载错误安全展示 | `<skill_load_warnings>` 只作为诊断信息 | `_skill/prompt.py` 相关测试 |
| prompt 成本统计 | 路由 prompt token、全量注入 token、节省率 | `scripts/run_skill_quality.py` |

量化数据落盘到 `test-results/skill-quality-summary.*`，包括 skill 数量、路由 prompt token、全量加载 token、渐进披露节省率。

### 维度 C - LLM 路由准确率

| 目标 | 覆盖点 | 主要文件 |
|------|--------|----------|
| 正例命中 | 文档生成、代码审查、echo、数据分析等 query 能选中正确 skill | `tests/test_skill_llm_integration.py` |
| 负例拒绝 | 天气、无关文件上传、空 query 返回 `should_call=false` | `tests/test_skill_llm_integration.py` |
| 大样本评测 | 120 条真实 LLM 路由样本，统计 TP/TN/FP/FN | `scripts/run_routing_eval.py` |

量化数据：Accuracy、Precision、Recall、F1、混淆矩阵、按类别/难度/skill 分组统计。大样本报告落盘到 `test-results/routing-eval-report.*`。

### 维度 D - Schema 与异常容错

| 目标 | 覆盖点 | 主要文件 |
|------|--------|----------|
| 幻觉 skill 拒绝 | LLM 返回不存在的 `skill_name` 会失败 | `tests/test_skill_llm_integration.py` |
| 类型校验 | `should_call`、`confidence`、`fields` 类型错误会失败 | `tests/test_skill_llm_integration.py` |
| 非 JSON 拒绝 | LLM 返回非 JSON 不进入后续链路 | `tests/test_skill_llm_integration.py` |
| 空目录兜底 | 没有可用 skill 时系统仍可输出空索引和诊断信息 | `tests/test_skill_boundary.py` |

量化数据：schema 错误数、解析失败数、load_errors 数、异常测试通过率。

### 维度 E - 字段抽取质量

| 目标 | 覆盖点 | 主要文件 |
|------|--------|----------|
| 本地字段兜底 | 中文 query 中提取 `filename`、`template_name`、`title`、`output_path` | `tests/test_skill_field_extraction.py` |
| 空值安全 | 空 query、无关键字、关键字无值不会产生脏字段 | `tests/test_skill_field_extraction.py` |
| LLM 字段对比 | 对比本地字段抽取与 LLM routing fields | `tests/test_skill_field_extraction.py` |
| 字段质量评测 | 字段样本 Precision/Recall | `tests/test_field_extraction_quality.py` |

量化数据：字段 Precision、Recall、错误样本、字段覆盖率。当前字段抽取是轻量兜底，不是最终路由器。

### 维度 F - 工具能力

| 目标 | 覆盖点 | 主要文件 |
|------|--------|----------|
| Word 文档生成 | `WordDocumentTool` 生成 `.docx` 并验证文件存在 | `tests/test_word_document_tool.py` |
| 默认字段兜底 | 缺少文件名或标题时使用默认值 | `tests/test_word_document_tool.py` |
| 测试 fake 兼容 | `tests/fakes/` 中 fake 包装真实工具供测试断言使用 | `tests/fakes/word_document_tool.py` |

生产可执行能力应放在 `tools/`，而不是放在 prompt adapter 里。

### 维度 G - QA 问答集质量

| 目标 | 覆盖点 | 主要文件 |
|------|--------|----------|
| 路由正确 | QA query 是否命中预期 skill | `tests/test_skill_qa.py` |
| 答案结构 | 是否包含必要步骤、配置、关键说明 | `tests/test_skill_qa.py`、`evals/qa_quality.py` |
| 语言一致性 | 中文 query 是否返回中文答案 | `evals/qa_quality.py` |
| 幻觉控制 | 不编造不存在的 `scripts/`、`references/`、`assets/` 路径 | `evals/qa_quality.py` |
| LLM Judge | 用真实模型做语义正确性、可执行性、严重错误判断 | `tests/test_skill_qa.py` |

量化数据落盘到 `test-results/qa-report.*`，包括综合评分、关键要素命中、本地确定性质量、LLM judge 分、幻觉数、严重错误数、token 和 latency。

### 维度 H - 运行指标与报告

| 报告 | 内容 |
|------|------|
| `test-results/test-report.*` | pytest 总体通过率、失败、跳过、耗时 |
| `test-results/quantitative-report.*` | pytest 运行时样本的混淆矩阵、token、latency、成功率 |
| `test-results/routing-eval-report.*` | 120 条真实 LLM 大样本路由评测 |
| `test-results/qa-report.*` | QA 问答集质量评测 |
| `test-results/skill-quality-summary.*` | skill 库存、prompt 预算、字段抽取质量 |

Token 统计优先使用供应商返回的真实 `usage`。供应商不返回时，`TokenTracker` 使用字符数估算，并标记为 estimated。

## 3. 自动化测试脚本建议

### 本地稳定测试

```bash
python3 -m pytest tests/ \
  --ignore=tests/test_skill_llm_integration.py \
  --ignore=tests/test_skill_qa.py \
  -v
```

用于日常开发和重构验证，不依赖远程 API。

### 真实 LLM 路由测试

```bash
python3 -m pytest tests/test_skill_llm_integration.py -v
python3 scripts/run_routing_eval.py --output-dir test-results
```

用于验证模型在真实供应商下的路由稳定性。

### QA 问答集测试

```bash
python3 -m pytest tests/test_skill_qa.py -v
```

用于验证选中 skill 后的答案质量。该测试依赖真实 LLM，可能因为模型输出质量低于阈值而失败；失败本身也是质量信号。

### 质量摘要刷新

```bash
python3 scripts/run_skill_quality.py --output-dir test-results
```

用于刷新 skill 数量、prompt token 成本、字段抽取质量等静态和半静态指标。

## 4. 当前边界

| 边界 | 影响 | 后续方向 |
|------|------|----------|
| LLM 是唯一正式路由器 | LLM 不可用时无法语义选 skill | 可增加 BM25/embedding 候选召回作为前置缩小集合 |
| 字段抽取是规则兜底 | 复杂表达可能提取不到 | 将字段 schema 与具体 skill 绑定，交给 LLM 结构化补全 |
| QA runner 不是 agent runtime | 只能评估答案质量，不能代表真实工具 loop | 后续接入真实 agent 后补充工具调用链路测试 |
| 大样本仍偏小 | 120 条能看趋势，不能代表全量用户分布 | 按真实 query 日志扩充到 500-1000 条 |
| 相近 skill 易混淆 | documents/docx/pdf/render 等边界需要更清晰 | 优化 description，并加入 hard negative 样本 |
