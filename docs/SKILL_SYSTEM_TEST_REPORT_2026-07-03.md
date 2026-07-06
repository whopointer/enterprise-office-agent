# Skill 系统测试汇报报告

> 原报告日期：2026-07-03  
> 本次更新：2026-07-06  
> 项目：enterprise-office-agent  
> 数据来源：`test-results/test-report.*`、`test-results/quantitative-report.*`、`test-results/routing-eval-report.*`、`test-results/qa-report.*`、`test-results/skill-quality-summary.*`  
> 测试口径：真实 LLM 路由评测、真实 LLM QA 问答集评测、运行时 token/latency 统计、skill 库质量摘要

## 1. 汇报结论

本轮重点重新测试了 Skill 系统在真实 LLM 下的路由和问答输出质量。系统链路可以跑通，路由整体可用，token usage 可以拿到真实供应商返回值；但在更严格的 QA 质量门禁下，部分答案被判定为不合格。

需要特别说明：`tests/test_skill_qa.py` 当前不是“只验证脚本能不能跑”的冒烟测试，而是质量门禁测试。只要真实 LLM 输出没有直接解决用户问题、步骤不完整、配置不可执行、存在隐蔽严重错误，测试就会失败。因此本轮 QA 存在失败用例，说明质量判定机制生效，而不是测试框架无法运行。

总体结论：

| 方向 | 最新结果 | 判断 |
|------|----------|------|
| QA 问答集测试 | 20 条样本，14 通过，7 failed test case，QA 综合分 76.0% | 链路可运行，输出质量仍需优化 |
| QA 质量维度 | 已覆盖技术正确性、步骤顺序、配置可执行性、文档标准、问题解决度、隐蔽严重错误 | 质量门禁已建立 |
| QA 路由准确率 | 90.0%，TP=17 / TN=1 / FP=1 / FN=1 | Render 场景整体可用，但仍有误路由和漏激活 |
| QA 输出执行 | 17 次执行，17 次成功 | 执行链路稳定 |
| QA Token 统计 | 路由 20 次 actual，执行 17 次 actual | 已接入真实 usage |
| 大样本路由评测 | 120 条，109 通过，Case Accuracy 90.8% | 明确意图稳定，模糊/否定意图较弱 |
| Skill 库加载 | 21 个 skill，0 加载错误 | skill 库可稳定发现和加载 |
| Prompt 成本 | 路由 prompt 约 2046 token；全量 body 注入约 60571 token | 渐进披露节省约 96.6% |
| 字段抽取 | 50 条，Precision/Recall 100% | 明确字段表达稳定 |

当前主要风险集中在三类：

1. 真实 LLM 有时倾向于反问用户，而不是直接给出可执行方案。
2. 模糊、否定、相近 skill 场景仍有误触发或漏激活。
3. 复杂部署答案中可能出现配置可执行性或隐蔽严重错误。

## 2. 本轮执行命令

本轮实际重新执行的核心测试命令：

```bash
python3 -m pytest tests/test_skill_qa.py -v
```

辅助验证命令：

```bash
python3 -m py_compile tests/test_skill_qa.py tests/test_qa_quality_eval.py evals/qa_quality.py
python3 -m pytest tests/test_qa_quality_eval.py -q
python3 -m pytest tests/test_skill_qa.py --collect-only -q
```

当前 `test-results/test-report.*` 对应的是 `tests/test_skill_qa.py` 的真实 LLM QA 测试，不是全量 `tests/` 测试。因此本报告不再沿用旧版“139 条全量 pytest 全通过”的结论。

执行过程中仍出现以下非阻断警告：

```text
skill name 'docx-report-generator' 与目录名 'word-report-generator-1.0.0' 不一致，建议保持一致
```

该警告不影响加载和测试执行，但建议后续统一目录名和 skill name，减少评测和人工排查时的歧义。

## 3. 报告文件总览

| 报告 | 位置 | 当前含义 |
|------|------|----------|
| QA pytest 汇总 | `test-results/test-report.md/json` | 本轮 `tests/test_skill_qa.py` 的 21 个 pytest item 结果 |
| 运行时量化 | `test-results/quantitative-report.md/json` | QA 运行中的路由、执行、token、延迟 |
| QA 问答集 | `test-results/qa-report.md/json` | 20 条 Render QA 的输出质量评分和失败原因 |
| 大样本路由 | `test-results/routing-eval-report.md/json` | 120 条真实 LLM 路由评测 |
| Skill 质量摘要 | `test-results/skill-quality-summary.md/json` | skill 库存、prompt 成本、字段抽取质量 |

## 4. QA pytest 结果

报告文件：

```text
test-results/test-report.md
test-results/test-report.json
```

| 指标 | 值 |
|------|----|
| pytest item 总数 | 21 |
| 通过 | 14 |
| 失败 | 7 |
| 跳过 | 0 |
| 错误 | 0 |
| 通过率 | 66.7% |
| 退出码 | 1 |
| 报告时间 | 2026-07-06 08:02:20 UTC |

失败用例：

| 用例 | 主要失败类型 |
|------|--------------|
| QA-01 | 本地质量不足，judge 质量不足 |
| QA-06 | judge 质量不足，存在严重问题 |
| QA-09 | 本地质量不足，judge 质量不足 |
| QA-10 | judge 质量不足 |
| QA-14 | judge 质量不足 |
| QA-18 | judge 质量不足，语言比例异常 |
| QA-19 | 路由错误 |

说明：这些失败表示真实 LLM 输出没有达到当前 QA 质量标准，并不表示测试脚本无法执行。`test_qa_summary_report` 已通过，说明测试过程能够完成汇总并落盘报告。

## 5. QA 问答集评测

报告文件：

```text
test-results/qa-report.md
test-results/qa-report.json
```

### 5.1 综合指标

| 指标 | 值 |
|------|----|
| 总用例数 | 20 |
| 正例数 | 19 |
| 实际执行答案数 | 17 |
| 失败用例数 | 8 |
| 路由准确率 | 90.0% |
| 关键要素命中率 | 69.6% |
| 本地确定性质量 | 71.0% |
| LLM Judge 语义质量 | 64.8% |
| 语言一致性 | 94.1% |
| 幻觉控制 | 100.0% |
| 严重错误控制 | 85.0% |
| QA 加权总分 | 76.0% |

### 5.2 质量判定维度

当前 QA 不做标准答案全文比对，而是组合以下维度判定答案是否可靠：

| 维度 | 判定方式 |
|------|----------|
| 技术正确性 | `technical_checks` + LLM judge 的 `technical_correctness` |
| 步骤顺序 | `ordered_steps` + LLM judge 的 `step_order` |
| 配置可执行性 | `config_checks` 解析配置块，例如 `render.yaml` |
| 产物/方案文档标准 | `document_standard` 检查章节、长度、必备内容 |
| 是否解决用户问题 | LLM judge 的 `problem_resolution` |
| 隐蔽严重错误 | `forbidden`、`technical_checks.must_not_include`、LLM judge 的 `hidden_critical_errors` |
| 幻觉引用 | 检查答案引用的 `scripts/`、`references/`、`assets/` 是否真实存在 |

### 5.3 失败原因分布

| 失败原因 | 数量 | 说明 |
|----------|------|------|
| `judge_quality` | 6 | LLM judge 认为答案没有达到语义质量阈值 |
| `local_quality` | 2 | 本地确定性规则未通过 |
| `critical_issue` | 1 | 存在足以导致失败的严重问题 |
| `missed_activation` | 1 | 应激活 skill 但未激活 |
| `routing` | 1 | 路由到了错误 skill |
| `language` | 1 | 中文比例异常或输出语言不符合预期 |

### 5.4 失败样本摘要

| ID | 状态 | 要素命中 | 本地质量 | Judge | 主要问题 |
|----|------|----------|----------|-------|----------|
| QA-01 | failed | 3/7 | 52% | 30% | 缺少 `PORT`、`npm`、`startCommand` 等关键部署要素，方案不完整 |
| QA-06 | failed | 6/6 | 100% | 40% | 本地要素满足，但 judge 发现复杂 `render.yaml` 方案存在严重问题 |
| QA-07 | missed_activation | 0/5 | 0% | 0% | 部署后验证场景未激活 `render-deploy` |
| QA-09 | failed | 3/5 | 52% | 50% | Cron/schedule 场景答案不够可执行 |
| QA-10 | failed | 2/5 | 69% | 40% | 静态站点部署方案不完整 |
| QA-14 | failed | 6/6 | 67% | 0% | Rails + PostgreSQL + Sidekiq 场景没有给出足够可执行方案 |
| QA-18 | failed | 4/6 | 71% | 30% | Go API + React 前端场景未直接解决问题，语言比例异常 |
| QA-19 | routing_failed | 0/5 | 0% | 0% | `network timeout` 故障排查被路由到 `cloudflare-deploy` |

### 5.5 QA Token 消耗

| 指标 | 值 |
|------|----|
| 路由 Token 平均 | 2102.8 |
| 路由 Token 总计 | 42056 |
| 执行 Token 平均 | 5129.1 |
| 执行 Token 总计 | 87194 |
| Token 来源 | actual usage |

结论：QA 链路可以稳定记录真实 token。当前主要问题不在 token 统计，而在答案质量和路由边界。

## 6. pytest 运行时量化报告

报告文件：

```text
test-results/quantitative-report.md
test-results/quantitative-report.json
```

这份报告只统计本轮 QA pytest 运行过程中 `RuntimeCollector` 显式记录的样本，不等同于 120 条大样本路由评测。

### 6.1 QA 路由混淆矩阵

| 指标 | 值 |
|------|----|
| 样本数 | 20 |
| TP | 17 |
| TN | 1 |
| FP | 1 |
| FN | 1 |
| Accuracy | 90.0% |
| Precision | 94.4% |
| Recall | 94.4% |

### 6.2 执行链路指标

| 指标 | 值 |
|------|----|
| 执行次数 | 17 |
| 成功次数 | 17 |
| 成功率 | 100.0% |
| Token 最小值 | 4410 |
| Token 最大值 | 6185 |
| Token 平均值 | 5129.1 |
| Token 总量 | 87194 |
| Token 来源 | actual 17 次 |
| 延迟最小值 | 3477.79 ms |
| 延迟最大值 | 23892.03 ms |
| 延迟平均值 | 12077.69 ms |
| 延迟 p50 | 11035.78 ms |

### 6.3 路由 Token

| 指标 | 值 |
|------|----|
| 路由 token 最小值 | 1946 |
| 路由 token 最大值 | 2498 |
| 路由 token 平均值 | 2102.8 |
| 路由 token 总量 | 42056 |
| 路由 token 来源 | actual 20 次 |

说明：本轮 QA 中记录到的路由和执行 token 均来自供应商真实 `usage`。

## 7. 真实 LLM 大样本路由评测

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
| Case Accuracy | 90.8% |
| TP | 74 |
| TN | 35 |
| FP | 8 |
| FN | 3 |
| Precision | 90.2% |
| Recall | 96.1% |
| 路由 Token 总消耗 | 250144 |
| 路由 Token 单次平均 | 2084.5 |
| Token 来源 | actual 120 次 |

### 7.1 按类别

| Category | Count | Passed | Accuracy |
|----------|------:|-------:|---------:|
| `document_generation` | 15 | 15 | 100.0% |
| `deployment` | 15 | 15 | 100.0% |
| `field_noise` | 10 | 10 | 100.0% |
| `irrelevant` | 20 | 19 | 95.0% |
| `other_skill` | 20 | 19 | 95.0% |
| `confusing_negative` | 20 | 16 | 80.0% |
| `ambiguous` | 20 | 15 | 75.0% |

明确意图的文档生成、部署和字段噪声样本表现稳定；准确率下降主要发生在 `ambiguous` 和 `confusing_negative`。

### 7.2 按难度

| Difficulty | Count | Passed | Accuracy |
|------------|------:|-------:|---------:|
| `easy` | 50 | 49 | 98.0% |
| `medium` | 30 | 29 | 96.7% |
| `hard` | 40 | 31 | 77.5% |

hard 样本仍是主要短板，说明复杂表达、否定表达和相近 skill 竞争仍需优化。

### 7.3 混淆对

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

路由层面的主要改进方向是减少负例误触发、减少文档类 skill 之间的竞争误判，并提升模糊表达下的激活稳定性。

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

结论：真实 skill 库可以稳定发现和加载，没有加载错误。

### 8.2 Prompt 成本

| 指标 | 值 |
|------|----|
| 路由 prompt token | 2046 |
| description token | 1682 |
| body token | 58525 |
| 全量注入 token | 60571 |
| 渐进披露节省率 | 96.6% |

结论：只把 skill 的 name 和 description 注入路由 prompt 是必要的。如果把全部 `SKILL.md` body 一次性塞入 prompt，成本会从约 2046 token 增加到约 60571 token，不适合作为默认策略。

### 8.3 字段抽取

| 指标 | 值 |
|------|----|
| 用例数 | 50 |
| 完全匹配率 | 100.0% |
| Precision | 100.0% |
| Recall | 100.0% |

说明：字段抽取结果来自当前数据集中的明确字段表达。它证明规则在这些样本上稳定，但不代表任意自然语言字段抽取都已经充分泛化。

## 9. 本轮测试暴露的问题

### 9.1 QA 输出质量问题

最明显的问题是部分回答没有直接解决用户问题，而是先追问更多信息。对于真实助手体验，这种行为不一定永远错误；但在当前 QA 标准中，用户问“怎么部署”时，答案至少应给出可执行的默认方案、配置示例、验证方法和必要假设。

典型失败：

- QA-01：Express 部署缺少 `PORT`、`npm`、`startCommand` 等关键要素。
- QA-09：Cron job 场景缺少足够可执行的 schedule/配置说明。
- QA-14：Rails + PostgreSQL + Sidekiq 场景回答不够完整。
- QA-18：Go API + React 前端场景没有直接给出部署方案。

### 9.2 路由边界问题

QA-19 中 `network timeout` 故障排查被路由到 `cloudflare-deploy`，说明部署类 skill 之间还存在相近场景竞争。大样本路由评测也显示 hard 样本准确率只有 77.5%，主要问题集中在模糊表达和否定表达。

### 9.3 复杂配置正确性问题

QA-06 本地检查得分 100%，但 LLM judge 给出 40%，并标记严重问题。这说明只靠关键词或 YAML 结构检查不足以判断复杂配置是否真正可执行，LLM-as-judge 或更强的配置验证器是必要的。

### 9.4 测试报告口径问题已修正

此前 QA 报告可能只统计有效输出，不完整覆盖负例、漏激活、路由错判或供应商异常。当前脚本已经把这些情况纳入 `_qa_results`，并在报告里通过 `status` 和 `failure_reasons` 区分。

## 10. 改进建议

### 10.1 优先优化 Render deploy skill 的回答策略

建议在 `render-deploy` 的 skill 指令中明确：

1. 用户信息不足时，也要先给出基于常见假设的可执行默认方案。
2. 追问应放在答案末尾，不能替代方案本身。
3. 部署类答案必须包含前提、配置、部署、验证、排错。
4. 涉及 `render.yaml` 时必须给出可执行字段，避免伪配置。

### 10.2 强化路由负例和相近 skill 判别

建议增加以下路由约束：

1. 对“不要生成”“不要部署”“只是命名”等否定意图提高拒绝优先级。
2. 对 `render-deploy`、`cloudflare-deploy`、`documents`、`docx-report-generator` 增加边界描述。
3. 对故障排查类 query 明确优先匹配对应平台 skill，而不是按关键词误触发其他部署 skill。

### 10.3 增强配置验证

当前 `config_checks` 已能解析 YAML 结构，但复杂配置还需要更强验证：

1. 对 Render service type、runtime、env、startCommand、buildCommand 做字段级校验。
2. 对 PostgreSQL、Redis、worker、cron 场景做组合规则校验。
3. 对密钥、环境变量、端口绑定做安全规则校验。

### 10.4 固化 QA 报告为质量门禁

建议后续把 QA 报告作为质量趋势数据，而不是只看 pytest pass/fail：

| 指标 | 建议门槛 |
|------|----------|
| 路由准确率 | 不低于 95% |
| 本地确定性质量 | 不低于 80% |
| LLM Judge 语义质量 | 不低于 80% |
| 严重错误控制 | 100% |
| 幻觉控制 | 100% |

当前 QA 加权总分为 76.0%，距离稳定可用还有提升空间。

## 11. 最终结论

本轮重新测试后，Skill 系统的基础链路已经具备可测性和可观测性：

- skill 加载正常，21 个 skill 无加载错误。
- 路由 prompt 使用渐进披露，成本控制合理。
- 路由和执行 token 均能获取真实供应商 usage。
- 120 条路由大样本达到 90.8% case accuracy。
- QA 测试已经能从技术正确性、步骤顺序、配置可执行性、文档标准、问题解决度、隐蔽严重错误等维度判断答案质量。

但从真实使用角度看，当前 QA 输出质量还没有达到稳定交付标准。主要问题不是链路跑不通，而是部分 skill 输出没有足够直接、完整、可执行。下一阶段应优先优化 `render-deploy` 的回答策略、复杂配置校验和相近 skill 路由边界。
