# Skill 中间件链路说明报告

> 日期：2026-07-03  
> 项目：enterprise-office-agent  
> 范围：`_skill/` 中间件、LLM 路由、执行器、适配器、指标采集与兜底机制

## 1. 总体结论

当前 Skill 系统采用“轻量发现 + 渐进披露 + LLM 路由 + 适配器执行 + 量化采集”的链路。

核心原则是：路由阶段只暴露 `name + description`，让大模型先判断是否需要调用 skill；只有选中 skill 后，执行器才把完整 `SKILL.md` body 交给适配器执行。这样可以降低 prompt 成本，也减少无关 skill 指令对模型判断的干扰。

当前系统没有本地关键词路由器，也没有旧版红线拦截模块。真实选择权在 `OpenAIChatSkillRouter`，本地侧主要负责 skill 发现、prompt 注入、schema 校验、执行兜底和指标采集。

## 2. 链路总览

```mermaid
flowchart TD
    A["用户 Query"] --> B["agent.field_extractor.extract_fields_from_query<br/>轻量字段预提取"]
    B --> C["_skill.discovery.FileSkillDiscovery<br/>扫描 skills/ 下的 SKILL.md"]
    C --> D["_skill.parser.parse_skill_file<br/>解析 frontmatter + body"]
    D --> E["_skill.models.SkillIndex<br/>构建 skill 索引"]
    E --> F["llm.skill_router.OpenAIChatSkillRouter<br/>构建 skills_catalog"]
    F --> G["OpenAI-compatible LLM<br/>只看 name + description 做路由"]
    G --> H["llm.schema.validate_llm_decision_payload<br/>校验 should_call / skill_name / fields"]
    H --> I{"should_call=true<br/>且 skill 存在?"}
    I -- "否" --> J["返回 decision<br/>不执行 skill"]
    I -- "是" --> K["core.executor.SkillExecutor<br/>构建完整执行 prompt"]
    K --> L["adapters.SkillAdapter<br/>OpenAI / LangChain / SpringAI / Callable"]
    L --> L1{"Adapter 是否具备<br/>tool runtime?"}
    L1 -- "否：普通 LLM/HTTP 执行" --> M["ExecutionResult<br/>output + metrics + context"]
    L1 -- "是：外部/未来工具型 runtime" --> T["校验 allowed-tools<br/>执行 tool / script loop"]
    T --> M
    M --> N["core.runtime_metrics.RuntimeCollector<br/>记录路由、token、延迟、成功率"]
```

## 3. 分层职责

| 层级 | 主要文件 | 职责 |
|------|----------|------|
| Skill 中间件 | `_skill/discovery.py`、`_skill/parser.py`、`_skill/middleware.py`、`_skill/prompt.py` | 从文件系统加载 skill，解析 `SKILL.md`，向 system prompt 注入轻量清单 |
| 数据模型 | `_skill/models.py` | 定义 `SkillDefinition`、`SkillIndex`、`TokenMetrics`、`ExecutionResult` 等纯数据结构 |
| 字段预提取 | `agent/field_extractor.py` | 从中文自然语言中提取 `filename`、`template_name`、`title`、`output_path` 等结构化字段 |
| LLM 路由 | `llm/skill_router.py`、`llm/schema.py` | 调用 OpenAI-compatible API，让模型选择 skill，并对返回 JSON 做本地 schema 校验 |
| 执行器 | `core/executor.py` | 组装完整 prompt，调用适配器，捕获异常，生成执行指标 |
| 适配器 | `adapters/skill_adapters.py` | 对接 OpenAI-compatible、LangChain、SpringAI HTTP、Callable 等执行后端；本地工具执行 loop 尚未实现 |
| 指标采集 | `core/runtime_metrics.py` | 记录混淆矩阵、token、延迟、执行成功率，并输出 Markdown/JSON 报告 |
| 评测脚本 | `scripts/run_routing_eval.py`、`scripts/run_skill_quality.py` | 生成大样本路由评测报告和 skill 质量摘要 |

## 4. 一次 Query 的详细流转

```mermaid
sequenceDiagram
    participant U as 用户
    participant FE as field_extractor
    participant D as FileSkillDiscovery
    participant R as OpenAIChatSkillRouter
    participant S as schema validator
    participant E as SkillExecutor
    participant A as Adapter
    participant M as RuntimeCollector

    U->>FE: 输入自然语言 query
    FE-->>R: 返回 known_fields 兜底字段
    R->>D: 读取 SkillIndex
    D-->>R: 返回 skills_catalog 来源
    R->>R: 构建只含 name + description 的路由 prompt
    R->>R: 调用 LLM，要求 JSON object
    R->>S: 校验 LLM 返回
    S-->>R: 返回规整后的 decision
    R->>M: 可记录路由 token usage
    alt 不需要调用 skill
        R-->>U: 返回 should_call=false
    else 需要调用 skill
        R->>E: 传入选中的 SkillDefinition 和 fields
        E->>E: 拼接完整 SKILL.md body 执行 prompt
        E->>A: adapter.execute(prompt, skill, context)
        A-->>E: output 或异常
        E->>M: 记录执行 token、latency、success
        E-->>U: 返回 ExecutionResult
    end
```

## 5. 渐进披露机制

系统分两阶段暴露 skill 信息：

| 阶段 | 暴露内容 | 目的 |
|------|----------|------|
| 路由阶段 | `skills_catalog=[{name, description}]` | 让 LLM 低成本判断该不该调用、调用哪个 skill |
| 执行阶段 | 选中 skill 的完整 `SKILL.md` body、用户 query、结构化字段 | 让执行适配器基于完整指令产出结果 |

最新质量报告显示：

| 指标 | 值 |
|------|----|
| Skill 数量 | 21 |
| 路由 prompt token | 2046 |
| 全量加载 token | 60571 |
| 渐进披露节省率 | 96.62% |

这说明当前链路没有把 21 个 skill 的完整正文一次性塞进路由 prompt，token 成本控制有效。

## 6. 安全措施

### 6.1 文件加载安全

| 措施 | 位置 | 作用 |
|------|------|------|
| 只扫描目录下的 `SKILL.md` | `_skill/discovery.py` | 非 skill 目录和普通文件不会进入索引 |
| `yaml.safe_load` | `_skill/parser.py` | 避免 YAML 解析执行任意对象 |
| UTF-8 校验 | `_skill/parser.py` | 非 UTF-8 文件直接拒绝 |
| 文件大小上限 10MB | `_skill/constants.py`、`_skill/parser.py` | 防止异常大文件拖垮加载 |
| skill name 格式校验 | `_skill/parser.py` | 只允许小写字母、数字、连字符，最长 64 字符 |
| description 截断 | `_skill/parser.py` | description 最长 1024 字符，避免路由 prompt 被单个 skill 撑爆 |
| compatibility 截断 | `_skill/parser.py` | compatibility 最长 500 字符 |
| 解析失败不影响其他 skill | `_skill/discovery.py` | 单个坏 skill 进入 `load_errors`，其他 skill 继续加载 |

### 6.2 Prompt 注入防护

| 措施 | 位置 | 作用 |
|------|------|------|
| 加载错误放入 `<skill_load_warnings>` | `_skill/prompt.py` | 明确告诉模型这些是诊断信息，不是执行指令 |
| 错误内容 JSON 编码 + HTML 转义 | `_skill/utils.py`、`_skill/prompt.py` | 防止错误文本被模型误当成 prompt 指令 |
| load warning 数量限制 | `_skill/constants.py` | 最多展示 20 条 |
| load warning 长度限制 | `_skill/constants.py` | 单条最多 1000 字符，超出截断 |
| 路由 prompt 只含 `name + description` | `llm/skill_router.py` | 减少正文中的复杂指令影响路由判断 |

### 6.3 LLM 返回校验

| 措施 | 位置 | 作用 |
|------|------|------|
| 要求 `response_format={"type": "json_object"}` | `llm/skill_router.py` | 降低非 JSON 输出概率 |
| 非 JSON 抛 `LLMRouterResponseError` | `llm/skill_router.py` | 不把不可解析文本当成有效决策 |
| `should_call` 必须是 boolean | `llm/schema.py` | 防止字符串、数字等弱类型误判 |
| `skill_name` 必须存在于 `SkillIndex` | `llm/schema.py` | 防止模型幻觉不存在的 skill |
| `should_call=true` 必须有 `skill_name` | `llm/schema.py` | 防止激活但没有目标 skill |
| `confidence` 规整到 0 到 1 | `llm/schema.py` | 防止越界置信度影响后续统计 |
| `fields` 必须是 object | `llm/schema.py` | 防止字段结构异常进入执行器 |

### 6.4 执行隔离与异常处理

| 措施 | 位置 | 作用 |
|------|------|------|
| `should_call=false` 不执行适配器 | `llm/skill_router.py` | 无匹配 skill 时直接返回，不触发执行 |
| skill 不存在不执行适配器 | `llm/skill_router.py` | 二次防御，避免空对象执行 |
| 适配器异常被捕获 | `core/executor.py` | 返回 `execution_success=false`，不中断整体流程 |
| 执行 prompt 有固定结构 | `core/executor.py` | skill 描述、用户请求、字段、正文分区明确 |
| 适配器统一协议 | `_skill/models.py` | 执行器只依赖 `execute(prompt, skill, context)` |

## 7. 保底措施

| 场景 | 保底行为 |
|------|----------|
| skills 来源目录不存在 | `FileSkillDiscovery` 返回空索引，并写入 `load_errors` |
| 单个 `SKILL.md` 解析失败 | 跳过该 skill，错误进入 `load_errors`，其他 skill 继续加载 |
| 没有可用 skill | prompt 中显示“暂无可用 skill”，路由模型应返回 `should_call=false` |
| 用户 query 有显式字段 | `field_extractor` 先提取字段，再作为 `known_fields` 给 LLM |
| LLM 返回字段不完整 | 本地预提取字段与 LLM fields 合并，本地字段作为兜底输入 |
| LLM 返回非 JSON | 抛出 `LLMRouterResponseError`，不进入执行 |
| LLM 幻觉 skill | `validate_llm_decision_payload` 拒绝 |
| LLM 决定不调用 skill | 返回 decision，`execution=None` |
| 适配器抛异常 | `SkillExecutor` 捕获异常，返回失败结果和错误信息 |
| 供应商返回 token usage | 记录真实 `actual` token |
| 供应商不返回 token usage | `TokenTracker` 使用字符数估算，标记 `estimated` |
| LangChain/SpringAI 返回 token_usage | 适配器提取 `usage/token_usage/response_metadata` 交给执行器统计 |

## 8. 当前边界和不足

| 边界 | 说明 |
|------|------|
| 没有本地红线拦截 | 旧版 `red_lines` 已移除，目前主要依赖 LLM 路由和 schema 校验 |
| 没有独立关键词路由器 | 本地字段提取不是路由器，不能替代 LLM 选 skill |
| 没有向量召回 | 当前按全量 `name + description` 目录给 LLM 判断，未接 BM25/embedding |
| references/assets 未自动分片召回 | 执行阶段加载完整 `SKILL.md` body，但 references/assets 的深度读取仍依赖 skill 指令和适配器能力 |
| 否定意图仍可能误触发 | 最新大样本中存在 `不要生成 Word` 却误选 `pdf` 的情况 |
| 相近 skill 会竞争 | `documents` 与 `docx-report-generator`、部署文档与 `render-deploy` 存在边界混淆 |
| `docx-report-generator` 目录名不一致 | skill name 与目录 `word-report-generator-1.0.0` 不一致，当前只 warning 不阻断 |

## 9. 可观测性

系统当前会输出以下报告：

| 报告 | 内容 |
|------|------|
| `test-results/test-report.md/json` | pytest 总体通过率和逐用例耗时 |
| `test-results/quantitative-report.md/json` | pytest 运行时路由混淆矩阵、执行成功率、token、延迟、adapter 分组 |
| `test-results/routing-eval-report.md/json` | 120 条真实 LLM 大样本路由评测 |
| `test-results/qa-report.md/json` | QA 问答集的路由、要素命中、语言一致性、幻觉、token |
| `test-results/skill-quality-summary.md/json` | skill 库存、prompt 成本、字段抽取质量 |

## 10. 建议改进

1. 给 `scripts/run_routing_eval.py` 增加进度输出，例如每 10 条打印一次，方便长跑观察。
2. 针对否定意图增加路由后校验，例如“不要生成 Word”“不用 Render”“不是部署”这类表达先做本地风险标记。
3. 强化相近 skill 的 description 边界，尤其是 `documents`、`docx-report-generator`、`render-deploy`、Notion 系列 skill。
4. 统一 `docx-report-generator` 的目录名与 SKILL.md name。
5. 后续如果 skill 数量继续增加，可以引入 BM25 或 embedding 召回，先缩小候选 skill，再交给 LLM 细判。
