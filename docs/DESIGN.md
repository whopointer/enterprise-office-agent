# DeepAgent Skill 机制设计文档

> 参考 AgentScope skill 机制复现 | 仅保留 LangChain / SpringAI 适配 | 三阶段低耦合 | D

## 1. 目标拆解

### 1.1 总目标

参考 AgentScope 的 skill 机制，用 deepagent 范式复现。仅保留 **LangChain** 和 **SpringAI** 两种框架适配，三阶段管线必须有明确的代码边界、低耦合、DSL 驱动、零硬编码。

### 1.2 子目标

```
1. 三阶段流水线
   ├── Discovery（发现）：扫描 skill 目录，解析元信息、reference、asset、红线规则
   ├── Activation（激活）：根据用户 query 匹配 skill，执行红线校验，决定是否激活
   └── Execution（执行）：加载 skill 上下文（reference + asset），适配框架执行

2. 测试 skill 完整性
   ├── reference：skill 间引用（如 skill_search 引用其他 skill）
   ├── asset：Word 文档生成（.docx template → 填充 → 输出）
   ├── skill_search：搜寻所有已注册 skill 的能力
   └── 触发判断：skill 是否被激活的决策逻辑 + 红线全满足才调用

3. 综合量化评估
   ├── Token 消耗：不同大小 skill 的 token 消耗对比（小 / 中 / 大 skill 各一个）
   ├── 调用准确率：skill 激活 / 拒绝 / 误激活 / 漏激活的统计
   ├── 上下文装载质量：reference / asset 是否按 DSL 正确展开和注入
   ├── 规则执行质量：红线命中、拦截、放行结果是否符合预期
   └── 输出量化报告
```

---

## 2. 三阶段定义

### 2.1 Discovery（发现阶段）

| 维度 | 说明 |
|------|------|
| **输入** | `skills_dir` 路径 |
| **输出** | `SkillIndex { skills[], ref_graph, asset_map, redline_rules }` |
| **职责** | 扫描文件系统 → 解析 SKILL.md frontmatter DSL → 构建 skill 间引用有向图 → 索引 asset 文件 → 提取红线规则 |
| **解耦手段** | 输出为纯数据 `SkillIndex`，下游阶段不感知文件系统 |
| **零硬编码** | skill 元信息全部来自 SKILL.md 的 YAML frontmatter，无代码内常量 |

### 2.2 Activation（激活阶段）

| 维度 | 说明 |
|------|------|
| **输入** | `SkillIndex` + `user_query` |
| **输出** | `MatchResult { skill, confidence, redline_pass, reason }` 或 `NoSkillMatched` / `RedLineViolation` |
| **职责** | 关键词 / 语义匹配 → 红线规则逐条校验 → 计算置信度 → 决定是否激活 |
| **解耦手段** | 不感知 skill 文件内容，只消费 Stage1 产出的 `SkillIndex` |
| **红线机制** | 红线 DSL 定义在 SKILL.md 中，如 `required_fields: [filename]` → 缺失即拒绝激活，返回 `RedLineViolation` |

### 2.3 Execution（执行阶段）

| 维度 | 说明 |
|------|------|
| **输入** | `MatchResult` + `adapter: LangChainAdapter \| SpringAIAdapter` |
| **输出** | `ExecutionResult { output, metrics: ExecutionMetrics, asset_paths }` |
| **职责** | 组装 prompt（skill body + reference 展开 + asset 注入）→ 调用框架适配器 → 记录执行指标 → 返回结果 |
| **解耦手段** | 框架通过 `Adapter` 接口抽象，Stage3 不直接 import langchain 或 springai |
| **量化评估** | `MetricsCollector` 统一采集 token、调用准确率、装载完整性、红线命中、适配器执行结果等指标 |

---

## 3. 三阶段耦合关系

```
Discovery ──( SkillIndex )──▶ Activation ──( MatchResult )──▶ Execution ──( ExecutionResult )──▶ User
     ▲                            ▲                               ▲
     │                            │                               │
  SKILL.md DSL               红线规则 DSL                    Adapter 接口
```

每阶段只依赖上游的**纯数据产物**，无函数调用耦合，可独立单元测试，可替换任一阶段实现。

---

## 4. SKILL.md DSL 规范

```yaml
---
name: skill_name                    # 唯一标识
description: 功能描述                 # 用于匹配
triggers:                           # 触发条件
  keywords: [word, docx]
  patterns: [create.*document]

red_lines:                          # 红线规则（全部满足才激活）
  - field: filename                 # 必须提供的字段名
    message: 缺少文件名参数
  - field: template_name
    message: 未指定模板

references:                         # 引用的其他 skill
  - skill_name

assets:                             # 资源文件
  - path: assets/template.docx
    type: word_document
    description: 报告模板

metrics:                            # 量化评估配置
  expected_skill: word_generator
  expected_activation: true
  expected_references: [skill_name]
  expected_assets: [assets/template.docx]

token_estimate:                     # token 估算
  system_prompt: 500
  per_reference: 200
  per_asset: 300
---
```

---

## 5. 测试 Skill 清单

| Skill | 验证维度 | 说明 |
|-------|---------|------|
| **word_generator** | asset | .docx 模板填充生成 Word 文档 |
| **skill_search** | reference + 搜寻 | 引用其他 skill，列出所有已注册 skill |
| **redline_demo** | 红线 | 定义多项红线，验证缺字段时拒绝激活 |
| **mockskill** | 基础 | 小 skill，用于 token 基线对比 |

---

## 6. 量化评估指标

量化标准不只统计 token 消耗，还要覆盖 skill 机制本身是否“选得准、拦得住、装得全、跑得通”。所有指标由 `MetricsCollector` 统一采集，按测试用例、skill 大小、框架适配器三个维度输出报告。

### 6.1 Token 消耗指标

| 指标 | 计算方式 |
|------|---------|
| `input_tokens` | system_prompt + 展开的 reference + asset 描述 + user_query |
| `output_tokens` | 框架返回的实际 token 数 |
| `total_tokens` | input + output |
| `overhead_pct` | (total - baseline_mockskill) / baseline_mockskill × 100% |

小 / 中 / 大 skill 各跑一次，输出 token 对比表。

### 6.2 Skill 调用准确率指标

| 指标 | 计算方式 |
|------|---------|
| `activation_accuracy` | (TP + TN) / 全部测试用例 |
| `precision` | TP / (TP + FP)，衡量被激活的 skill 中有多少是正确调用 |
| `recall` | TP / (TP + FN)，衡量应该激活的 skill 有多少被成功激活 |
| `false_positive_rate` | FP / (FP + TN)，衡量误激活比例 |
| `false_negative_rate` | FN / (FN + TP)，衡量漏激活比例 |
| `confidence_avg` | 所有正确激活用例的平均置信度 |

判定口径：

| 类型 | 含义 |
|------|------|
| TP | 期望激活某 skill，实际也激活了同一个 skill |
| TN | 期望不激活，实际返回 `NoSkillMatched` 或 `RedLineViolation` |
| FP | 期望不激活或期望激活其他 skill，但实际激活了错误 skill |
| FN | 期望激活某 skill，但实际未激活 |

### 6.3 红线规则指标

| 指标 | 计算方式 |
|------|---------|
| `redline_block_rate` | 正确拦截的红线用例 / 应拦截红线用例 |
| `redline_pass_rate` | 正确放行的合法用例 / 应放行合法用例 |
| `redline_false_block_rate` | 被错误拦截的合法用例 / 应放行合法用例 |
| `redline_reason_match_rate` | 返回的 `reason` 与预期红线 message 匹配的比例 |

### 6.4 Reference / Asset 装载指标

| 指标 | 计算方式 |
|------|---------|
| `reference_load_rate` | 正确展开的 reference 数 / DSL 声明 reference 数 |
| `asset_load_rate` | 正确注入的 asset 数 / DSL 声明 asset 数 |
| `missing_reference_count` | DSL 声明但未成功展开的 reference 数 |
| `missing_asset_count` | DSL 声明但未成功注入的 asset 数 |
| `context_integrity_pass` | skill body、reference、asset 描述均完整时为 true |

### 6.5 执行与适配器指标

| 指标 | 计算方式 |
|------|---------|
| `execution_success_rate` | 成功返回 `ExecutionResult` 的用例 / 已激活用例 |
| `adapter_success_rate` | 按 LangChain / SpringAI 分组统计的执行成功率 |
| `latency_ms_avg` | 框架适配器调用平均耗时 |
| `artifact_success_rate` | 期望产物（如 .docx）成功生成并存在的比例 |

### 6.6 报告输出

最终报告至少包含：

```
1. Token 消耗对比表：按 skill 大小、阶段、适配器分组
2. Skill 调用混淆矩阵：TP / TN / FP / FN
3. 红线规则结果表：命中规则、拦截结果、reason 是否匹配
4. Reference / Asset 装载完整性表
5. LangChain / SpringAI 适配器执行成功率与耗时对比
```
