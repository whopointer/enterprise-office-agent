# Skill 系统测试汇报报告

> 日期：2026-07-03  
> 项目：enterprise-office-agent  
> 数据来源：`test-results/test-report.*`、`test-results/quantitative-report.*`、`test-results/routing-eval-report.*`、`test-results/qa-report.*`、`test-results/skill-quality-summary.*`  
> 测试口径：包含完整 pytest、真实 LLM 路由评测、QA 问答集评测和 skill 质量摘要

## 1. 汇报结论

本轮测试已经跑通完整 Skill 系统链路，包含本地单元/契约测试、真实 LLM 路由、真实 LLM QA 输出、prompt 成本和 token usage 统计。

总体结论：

| 方向 | 最新结果 | 判断 |
|------|----------|------|
| pytest 全量测试 | 139 条，139 通过 | 基础链路和契约稳定 |
| 大样本 LLM 路由 | 120 条，109 通过 | 整体可用，复杂边界仍需优化 |
| pytest 运行时路由 | 27 条，Accuracy 92.59% | 集成链路健康 |
| QA 问答集 | 19 条有效输出记录，综合分 87.55% | 输出质量可用，但结构完整度有提升空间 |
| Skill 库加载 | 21 个 skill，0 加载错误 | 真实 skill 库可稳定加载 |
| 字段抽取 | 50 条，Precision/Recall 100% | 明确字段表达稳定 |
| Token 统计 | 路由和执行均可记录 actual usage | 真实 token 统计已接入 |

当前主要风险集中在三类：模糊意图、否定意图、相近 skill 边界。

## 2. 本轮执行命令

```bash
python3 -m pytest tests/ -v
python3 scripts/run_routing_eval.py --output-dir test-results
python3 scripts/run_skill_quality.py --output-dir test-results
```

执行过程中出现 1 个非阻断警告：

```text
skill name 'docx-report-generator' 与目录名 'word-report-generator-1.0.0' 不一致，建议保持一致
```

该警告不影响加载和测试通过，但后续建议统一目录名，避免人工排查和评测数据混淆。

## 3. 报告文件总览

| 报告 | 位置 | 主要内容 |
|------|------|----------|
| pytest 汇总 | `test-results/test-report.md/json` | 139 条测试用例的通过率和耗时 |
| 运行时量化 | `test-results/quantitative-report.md/json` | pytest 中显式记录的路由、执行、token、延迟 |
| 大样本路由 | `test-results/routing-eval-report.md/json` | 120 条真实 LLM 路由评测 |
| QA 问答集 | `test-results/qa-report.md/json` | 真实输出质量、要素命中、语言一致性、幻觉检测 |
| Skill 质量摘要 | `test-results/skill-quality-summary.md/json` | skill 库存、prompt 成本、字段抽取质量 |

## 4. pytest 全量测试结果

报告文件：

```text
test-results/test-report.md
test-results/test-report.json
```

| 指标 | 值 |
|------|----|
| 总用例 | 139 |
| 通过 | 139 |
| 失败 | 0 |
| 跳过 | 0 |
| 错误 | 0 |
| 通过率 | 100.0% |
| 退出码 | 0 |
| 总耗时 | 373.58 秒 |

覆盖范围：

| 模块 | 覆盖内容 |
|------|----------|
| `_skill/` | Discovery、Parser、Prompt 注入、多 source、load warning、安全转义 |
| `llm/` | LLM 路由、schema 校验、非法响应、幻觉 skill、confidence 规整、真实 token usage |
| `core/` | SkillExecutor、TokenTracker、RuntimeCollector、混淆矩阵、p95、actual/estimated token |
| `adapters/` | OpenAICompatible、LangChain、SpringAI、WordDocument、Callable |
| `agent/` | 中文字段抽取 |
| `evals/` | 路由评测数据集和 runner 的本地校验 |
| `tests/test_skill_qa.py` | 真实 LLM 问答集评测 |

结论：基础设施、路由契约、执行器、适配器、报告生成链路均通过自动化测试。

## 5. pytest 运行时量化报告

报告文件：

```text
test-results/quantitative-report.md
test-results/quantitative-report.json
```

这份报告只统计 pytest 运行过程中 `RuntimeCollector` 显式记录的样本，不等同于 120 条大样本路由评测。

### 5.1 路由健康检查

| 指标 | 值 |
|------|----|
| 样本数 | 27 |
| TP | 21 |
| TN | 4 |
| FP | 0 |
| FN | 2 |
| Accuracy | 92.59% |
| Precision | 100.0% |
| Recall | 91.30% |

27 条样本包含 LLM 集成测试和 QA 问答集测试中的路由记录。两个 FN 来自 QA 用例中应激活 `render-deploy` 但模型未激活的样本。

### 5.2 执行链路指标

| 指标 | 值 |
|------|----|
| 执行次数 | 32 |
| 成功次数 | 29 |
| 成功率 | 90.62% |
| Token 最小值 | 66 |
| Token 最大值 | 6645 |
| Token 平均值 | 2884.3 |
| Token 总量 | 92298 |
| Token 来源 | actual 18 次，estimated 14 次 |
| 延迟最小值 | 0.0 ms |
| 延迟最大值 | 29415.51 ms |
| 延迟平均值 | 8483.29 ms |
| 延迟 p50 | 5276.37 ms |
| 延迟 p95 | 26723.8 ms |

执行失败主要来自测试中故意构造的失败路径，例如无效 adapter、无效 SpringAI endpoint 等，用于验证异常兜底。

### 5.3 路由 Token

| 指标 | 值 |
|------|----|
| 路由 token 最小值 | 400 |
| 路由 token 最大值 | 2375 |
| 路由 token 平均值 | 1666.1 |
| 路由 token 总量 | 44984 |
| 路由 token 来源 | actual 27 次 |

说明：本轮 pytest 中所有记录到的路由 token 都来自供应商返回的真实 `usage`。

## 6. 真实 LLM 大样本路由评测

报告文件：

```text
test-results/routing-eval-report.md
test-results/routing-eval-report.json
```

整体指标：

| 指标 | 值 |
|------|----|
| 总样本数 | 120 |
| 通过样本数 | 109 |
| Case Accuracy | 90.83% |
| TP | 74 |
| TN | 35 |
| FP | 8 |
| FN | 3 |
| Precision | 90.24% |
| Recall | 96.10% |
| 平均延迟 | 3158.64 ms |
| 正确样本平均置信度 | 0.6514 |
| 错误样本平均置信度 | 0.6318 |

### 6.1 按类别

| Category | Count | Passed | Accuracy |
|----------|------:|-------:|---------:|
| `document_generation` | 15 | 15 | 100.0% |
| `deployment` | 15 | 15 | 100.0% |
| `field_noise` | 10 | 10 | 100.0% |
| `irrelevant` | 20 | 19 | 95.0% |
| `other_skill` | 20 | 19 | 95.0% |
| `confusing_negative` | 20 | 16 | 80.0% |
| `ambiguous` | 20 | 15 | 75.0% |

明确意图的 `document_generation`、`deployment`、`field_noise` 表现稳定；准确率下降主要发生在 `ambiguous` 和 `confusing_negative`。

### 6.2 按难度

| Difficulty | Count | Passed | Accuracy |
|------------|------:|-------:|---------:|
| `easy` | 50 | 49 | 98.0% |
| `medium` | 30 | 29 | 96.67% |
| `hard` | 40 | 31 | 77.5% |

hard 样本是当前主要短板，说明复杂表达、否定表达和相近 skill 竞争仍需优化。

### 6.3 路由 Token

| 指标 | 值 |
|------|----|
| 路由 token 最小值 | 1920 |
| 路由 token 最大值 | 2733 |
| 路由 token 平均值 | 2084.5 |
| 路由 token 总量 | 250144 |
| 路由 token 来源 | actual 120 次 |

本轮大样本路由评测的 token 全部来自供应商真实 `usage`。

### 6.4 失败样本

| ID | Query | Expected | Actual | 问题类型 |
|----|-------|----------|--------|----------|
| ROUTE-046 | 生成语音识别处理方案 | `speech` | `-` | FN，未激活 |
| ROUTE-066 | 生成一个健身计划 | `-` | `docx-report-generator` | FP，无关请求误触发 |
| ROUTE-077 | 帮我生成部署检查清单 | `docx-report-generator` | `-` | FN，模糊文档请求未激活 |
| ROUTE-081 | 给这个项目写发布文档 | `docx-report-generator` | `documents` | 文档类 skill 混淆 |
| ROUTE-085 | 帮我输出 render.yaml 说明文档 | `docx-report-generator` | `render-deploy` | 文档生成与部署 skill 混淆 |
| ROUTE-088 | 做一份部署 SOP 文档 | `docx-report-generator` | `documents` | 文档类 skill 混淆 |
| ROUTE-090 | 帮我整理发布流程 | `docx-report-generator` | `-` | FN，模糊表达未激活 |
| ROUTE-093 | 帮我看一下这个 report.pdf，不要生成 Word | `-` | `pdf` | FP，否定意图误触发 |
| ROUTE-097 | 帮我审查部署脚本，不要上线 | `-` | `security-best-practices` | FP，否定意图误触发 |
| ROUTE-099 | 我想创建一个叫 RenderReport 的类 | `-` | `docx-report-generator` | FP，关键词误触发 |
| ROUTE-107 | 我想把文档部署到网站上 | `-` | `cloudflare-deploy` | FP，负例误触发 |

混淆对统计：

| Pair | Count |
|------|------:|
| `- -> docx-report-generator` | 2 |
| `docx-report-generator -> -` | 2 |
| `docx-report-generator -> documents` | 2 |
| `- -> cloudflare-deploy` | 1 |
| `- -> pdf` | 1 |
| `- -> security-best-practices` | 1 |
| `docx-report-generator -> render-deploy` | 1 |
| `speech -> -` | 1 |

## 7. QA 问答集评测

报告文件：

```text
test-results/qa-report.md
test-results/qa-report.json
```

说明：pytest 中实际跑了 QA-01 到 QA-20。`qa-report` 汇总了 19 条有效输出质量记录；其中阴性对照样本只参与路由/拒绝判断，没有进入输出质量明细。

| 指标 | 值 |
|------|----|
| 有效记录数 | 19 |
| 路由准确率 | 89.47% |
| 结构完整度 | 72.55% |
| 语言一致性 | 89.47% |
| 幻觉控制 | 100.0% |
| 路由 token 平均值 | 2090.6 |
| 路由 token 总量 | 39722 |
| 执行 token 平均值 | 4783.1 |
| 执行 token 总量 | 90879 |
| 综合评分 | 87.55% |

### 7.1 QA 主要问题

| 问题 | 表现 |
|------|------|
| 路由 FN | QA-07、QA-19 未激活 `render-deploy` |
| 结构要素漏项 | QA-01、QA-04、QA-10、QA-15、QA-18 等存在 expected elements 未命中 |
| 中文比例偏低 | 部分输出混入大量英文配置项，中文比例低于预期 |
| 幻觉引用 | 当前未发现，幻觉控制 100% |

结论：QA 输出整体可用，但结构完整度只有 72.55%，说明仅“选对 skill”还不够，后续需要加强输出结构约束和关键要素覆盖。

## 8. Skill 质量摘要

报告文件：

```text
test-results/skill-quality-summary.md
test-results/skill-quality-summary.json
```

### 8.1 Skill 库存

| 指标 | 值 |
|------|----|
| Skill 数量 | 21 |
| 加载错误数 | 0 |
| Discovery 耗时 | 13.36 ms |
| references 目录数 | 15 |
| assets 目录数 | 14 |
| scripts 目录数 | 9 |
| description 平均长度 | 313.0 字符 |
| body 平均长度 | 11100.6 字符 |

### 8.2 Prompt 成本

| 指标 | 值 |
|------|----|
| 路由 prompt 字符数 | 7924 |
| 路由 prompt token | 2046 |
| description token | 1682 |
| body token 总量 | 58525 |
| 全量加载 token | 60571 |
| 渐进披露节省率 | 96.62% |

结论：渐进披露有效。路由阶段只注入轻量 catalog，如果全量加载所有 body，token 成本会显著放大。

### 8.3 字段抽取质量

| 指标 | 值 |
|------|----|
| 样本数 | 50 |
| Exact Match Rate | 100.0% |
| Precision | 100.0% |
| Recall | 100.0% |

覆盖字段：

| 字段 | 示例 |
|------|------|
| `filename` | `weekly.docx`、`reports/q2.docx` |
| `template_name` | `standard-report`、`finance-v1` |
| `title` | `项目周报`、`Q2经营分析` |
| `output_path` | `output/monthly.pdf`、`dist/report.docx` |
| `date` | `2026-07-03`、`2026年07月03日` |
| `report_type` | `周报`、`季报` |
| `format` | `docx`、`pdf`、`markdown` |
| `language` | `中文`、`英文`、`中英双语` |

说明：当前字段抽取对明确表达稳定，但隐式字段、跨句字段和更复杂自然语言表达仍需扩充样本。

## 9. 当前完成度

| 能力 | 状态 | 说明 |
|------|------|------|
| Skill Discovery | 已完成 | 21 个真实 skill，0 加载错误 |
| Skill 路由 | 已完成基础评测 | 120 条真实 LLM 样本，Accuracy 90.83% |
| Skill 执行 | 已完成链路测试 | prompt 构建、adapter 调用、失败兜底均覆盖 |
| Adapter contract | 已覆盖 | OpenAI、LangChain、SpringAI、Word、Callable |
| Token 统计 | 已支持 | 路由和执行均优先记录供应商 actual usage |
| Runtime 报告 | 已支持 | pytest 自动落盘 test-report 和 quantitative-report |
| 大样本评测 | 已支持 | 独立脚本生成 routing-eval-report |
| QA 输出质量 | 已初步支持 | 19 条有效输出质量记录，综合分 87.55% |

## 10. 风险与改进建议

| 风险 | 当前表现 | 建议 |
|------|----------|------|
| 模糊表达下路由准确率下降 | ambiguous 20 条通过 15 条 | 强化 skill description 边界，增加 hard/ambiguous 样本 |
| 否定意图误触发 | `不要生成 Word`、`不要上线` 仍可能触发 skill | 增加否定意图识别或路由后校验 |
| 相近 skill 竞争 | `documents` vs `docx-report-generator`、部署文档 vs `render-deploy` | 明确 skill 职责边界，必要时增加二次判别 |
| 关键词误触发 | `RenderReport` 误触发文档生成 | 对专有名词、类名、解释类 query 增加负例训练/评测 |
| QA 结构完整度不足 | element_hit_rate 72.55% | 执行 prompt 中强化必须覆盖的输出结构 |
| `docx-report-generator` 命名不一致 | 目录名与 `SKILL.md` name 不一致 | 统一目录名或在文档中明确映射 |
| 长跑脚本无进度 | `run_routing_eval.py` 120 条执行期间无逐条输出 | 增加每 N 条进度日志 |

## 11. 下一阶段计划

建议优先推进：

1. 针对 11 条大样本失败用例优化 skill description 和路由 prompt。
2. 增加否定意图后处理，覆盖“不用、不要、不是、仅解释、只是了解”等表达。
3. 扩充 QA 问答集，按 skill 类型分别评估输出结构完整度。
4. 给 `run_routing_eval.py` 增加进度输出和失败重试策略。
5. 统一 `docx-report-generator` 的目录名与 skill name。
6. 后续在 skill 数量扩大后，引入 BM25 或向量召回，先缩小候选集再交给 LLM 路由。

## 12. 附录：报告路径

```text
test-results/test-report.md
test-results/quantitative-report.md
test-results/routing-eval-report.md
test-results/qa-report.md
test-results/skill-quality-summary.md
```
