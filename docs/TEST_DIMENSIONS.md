# Skill 系统测试维度文档

> 最后更新: 2026-07-02 | 测试用例总数: 51 | 通过率: 100%

## 1. 测试架构

```
                    _skill/ 中间件
                   (加载 + 注入 prompt)
                          │
                          ▼
              OpenAIChatSkillRouter (llm/)
              LLM 选 skill → schema 校验
                          │
                          ▼
              SkillExecutor (core/)
              构建 prompt → 调 adapter
                          │
                          ▼
              4 种 Adapter (adapters/)
```

## 2. 测试维度全景

### 维度 A — 路由准确度（13 条，全真实 LLM）

| 场景 | 测试 | 文件 |
|------|------|------|
| TP — LLM 选中文 query 命中 document-generator | `test_llm_routes_to_document_generator` | `test_skill_llm_integration.py` |
| TP — LLM 选代码审查命中 code-reviewer | `test_llm_routes_to_code_reviewer` | 同上 |
| TP — LLM 选 simple-echo | `test_llm_routes_to_simple_echo` | 同上 |
| TP — LLM 选 data-analyzer | `test_llm_routes_to_data_analyzer` | 同上 |
| TN — 天气 query 拒绝 | `test_llm_rejects_irrelevant_weather_query` | 同上 |
| TN — 文件上传 query 拒绝 | `test_llm_rejects_irrelevant_file_upload_query` | 同上 |
| TN — 空 query 拒绝 | `test_llm_rejects_empty_query` | 同上 |

**混淆矩阵**：7 条路由评测自动计算 TP/TN/FP/FN，落盘到 `quantitative-report.md`。

### 维度 B — 字段提取质量（9 条）

| 场景 | 测试 | 文件 |
|------|------|------|
| 正则提取 filename（5 种中文写法） | `test_field_extractor_reads_filename_from_chinese_query` | `test_skill_field_extraction.py` |
| 正则提取 template_name（3 种写法） | `test_field_extractor_reads_template_name_from_chinese_query` | 同上 |
| 正则同时提取两个字段 | `test_field_extractor_reads_both_fields` | 同上 |
| 空 query → 空 dict | `test_field_extractor_handles_empty_query` | 同上 |
| 无关键字 → 空 dict | `test_field_extractor_handles_no_keywords` | 同上 |
| 关键字在但无值 → 空 dict | `test_field_extractor_handles_keyword_without_value` | 同上 |
| LLM 从自然语言提取字段 | `test_llm_extracts_filename_from_natural_language` | 同上 |
| 同 query 正则 vs LLM 对比 | `test_llm_vs_regex_field_extraction_comparison` | 同上 |
| LLM 识别 code-reviewer 请求并提取字段 | `test_llm_reports_fields_for_code_review` | 同上 |

### 维度 C — LLM 异常容错（4 条）

| 场景 | 测试 | 文件 |
|------|------|------|
| LLM 幻觉不存在的 skill_name → `LLMDecisionSchemaError` | `test_schema_rejects_hallucinated_skill_name` | `test_skill_llm_integration.py` |
| `should_call` 非 boolean → 拒绝 | `test_schema_rejects_invalid_should_call_type` | 同上 |
| `confidence` 非 number → 拒绝 | `test_schema_rejects_invalid_confidence_type` | 同上 |
| LLM 返回非 JSON → `LLMRouterResponseError` | `test_llm_parse_non_json_raises_error` | 同上 |

### 维度 D — 执行链路完整性（6 条，本地）

| 场景 | 测试 | 文件 |
|------|------|------|
| prompt 包含 skill 名、描述、body、用户请求 | `test_execution_builds_prompt_with_skill_body` | `test_skill_execution.py` |
| 结构化字段出现在 prompt 中 | `test_execution_passes_fields_to_prompt` | 同上 |
| Token 估算（input/output/total） | `test_execution_records_token_metrics` | 同上 |
| Latency 记录 > 0 | `test_execution_records_latency` | 同上 |
| 适配器抛异常 → execution_success=False | `test_execution_adapter_error_is_captured` | 同上 |
| TokenTracker overhead 计算 | `test_token_tracker_overhead_calculation` | 同上 |

### 维度 E — 适配器全覆盖（8 条）

| 适配器 | 测试 | 文件 |
|--------|------|------|
| `WordDocumentSkillAdapter` | 真实生成 .docx + 验证文件存在 | `test_skill_adapters.py` |
| `WordDocumentSkillAdapter` | 默认文件名 skill-output.docx | 同上 |
| `OpenAICompatibleSkillAdapter` | 真实调大模型 + 返回内容 > 0 | 同上 |
| `LangChainSkillAdapter` | invoke() 方法 runner | 同上 |
| `LangChainSkillAdapter` | callable runner（退到 __call__） | 同上 |
| `LangChainSkillAdapter` | 无效 runner → 执行失败不崩溃 | 同上 |
| `SpringAIHttpAdapter` | 无效 URL → 连接错误不崩溃 | 同上 |
| `CallableSkillAdapter` | skill name + context 完整传递 | 同上 |

### 维度 F — 边界与鲁棒性（7 条，本地）

| 场景 | 测试 | 文件 |
|------|------|------|
| 空 skills 目录 → 空 SkillIndex | `test_discovery_empty_directory_all_methods_safe` | `test_skill_boundary.py` |
| 超长 description 被截断 | `test_discovery_very_long_description_is_truncated` | 同上 |
| 非法 skill 名 → load_errors | `test_parser_rejects_invalid_skill_names` | 同上 |
| 无 description → 解析失败 | `test_parser_rejects_skill_without_description` | 同上 |
| 超大 body 不崩溃 | `test_discovery_handles_very_long_skill_body` | 同上 |
| 非法 YAML → 正常 skill 仍加载 | `test_discovery_handles_unparseable_frontmatter` | 同上 |
| 无正文 skill 正常加载 | `test_skill_without_body_still_loads` | 同上 |

### 维度 G — Discovery 完整性（8 条，本地）

| 场景 | 测试 | 文件 |
|------|------|------|
| 解析 name / description / allowed-tools / body / license | `test_discovery_parses_name_description_and_allowed_tools` | `test_skill_discovery.py` |
| SkillIndex 方法正常工作 | `test_discovery_builds_skill_index` | 同上 |
| 空目录不报错 | `test_discovery_handles_empty_directory` | 同上 |
| 非 skill 目录被跳过 | `test_discovery_skips_non_skill_directories` | 同上 |
| 非法 SKILL.md 不崩溃，正常 skill 仍加载 | `test_discovery_handles_unparseable_skill_without_crashing` | 同上 |
| 来源目录不存在 → load_errors | `test_discovery_source_does_not_exist` | 同上 |
| 非法 skill 名被拒绝 | `test_skill_name_validation_rejects_invalid_names` | 同上 |
| 多 source 同名覆盖 | `test_multi_source_skill_override` | 同上 |

### 维度 H — 量化指标（自动落盘）

每次 `pytest` 运行自动输出到 `test-results/`：

| 报告 | 内容 |
|------|------|
| `test-report.json/.md` | 51 条 pass/fail 明细 + 耗时 |
| `quantitative-report.json/.md` | 混淆矩阵 (TP/TN/FP/FN) + Accuracy/Precision/Recall |
| | Token 消耗 (min/max/avg/total) |
| | 延迟 (min/max/avg/p50/p95) |
| | 按 skill 分组：执行次数 / 平均 Token / 平均延迟 / 成功率 |
| | 按 adapter 分组：执行次数 / 平均 Token / 平均延迟 / 成功率 |
| | 逐次执行明细表 |

### 维度 I — 问答集测试（新增，待实现）

**目的**：测试 LLM 在选中两个不同特征 skill 后的执行输出质量，对比技能复杂度对结果的影响。

**选中 skill**：

| Skill | 特征 | 来源 |
|-------|------|------|
| `word-report-generator-1.0.0` | references=2，assets=0，body 轻量 | 文档生成 |
| `render-deploy` | references=10，assets=8，body 重 | 部署（高资源 skill） |

**测试场景**：

| 编号 | 问答对 | 期望 skill | 标准输出要点 |
|------|--------|-----------|-------------|
| QA-01 | "帮我生成一份项目周报" | word-report-generator-1.0.0 | 含标题、时间、进展、问题、下周计划 |
| QA-02 | "帮我部署一个 Node.js 应用到 Render" | render-deploy | 含 blueprint 配置、服务类型、部署步骤 |
| QA-03 | "生成一份 Q2 总结 docx 文件" | word-report-generator-1.0.0 | 含季度数据、图表描述、文件名 .docx |
| QA-04 | "把我的 Django 服务部署上线到 Render" | render-deploy | 含 python-django.yaml asset 引用、环境变量 |
| QA-05 | "用户说帮我生成报告但不指定文件名" | word-report-generator-1.0.0 | 应追问或使用默认文件名 |

**评价维度**：

| 维度 | 评价方式 | 标准 |
|------|---------|------|
| skill 选择正确率 | 对比 expected vs actual skill_name | =100% |
| 输出结构完整性 | 检查输出是否包含关键要素（标题/步骤/文件名） | 每项 0/1 分 |
| 输出语言一致性 | 中文输入 → 中文输出 | 中文比例 > 80% |
| 技能适配度 | 高资源 skill 是否产出更详细的输出 | render-deploy 输出长度 > word-report-generator |
| token 效率 | 同上 query，高资源 skill token 开销 | 记录并对比 |
| 幻觉检测 | 输出是否编造不存在的脚本路径或配置 | 0 处虚构引用 |

**评分标准**：

| 指标 | 权重 | 计算方式 |
|------|------|---------|
| 路由准确率 | 30% | 选对 skill 的 case 数 / 总 case 数 |
| 结构完整度 | 30% | 各 case 关键要素命中分之和 / 总要素数 |
| 语言一致性 | 10% | 中文输出 case 数 / 需中文输出的 case 数 |
| 幻觉控制 | 20% | (总 case 数 - 幻觉 case 数) / 总 case 数 |
| token 效率 | 10% | 1 - (平均 token / 基线 token) |

**建议实现位置**：新文件 `tests/test_skill_qa.py`，使用真实 `OpenAIChatSkillRouter` + `OpenAICompatibleSkillAdapter`。

## 3. LLM 调用 vs 本地逻辑

| 类型 | 条数 | 调大模型 |
|------|------|----------|
| 真实 LLM 集成 | 22 | ✅（每次约 1.5-5s） |
| 纯本地逻辑 | 29 | ❌（毫秒级） |

LLM 调用集中在：`test_skill_llm_integration.py`（13 条）、`test_skill_field_extraction.py`（3 条）、`test_skill_adapters.py`（1 条 OpenAI 适配器）。问答集测试（5 条）加入后 LLM 调用将增至 27 条。

无 API_KEY 时 LLM 测试自动 skip，29 条本地测试仍可全量运行。

## 4. 已知局限

| 局限 | 影响 |
|------|------|
| 测试 skill 通过 `build_pipeline_test_skills` 手造，具备完整格式 | 测试覆盖基础设施，不代表真实 skill 的全部行为 |
| LLM 路由是唯一 skill 选择方式 | 无降级路径，LLM 不可用时系统无法选 skill |
| references/ 和 assets/ 目录文件未被 pipeline 自动读取注入 | 渐进披露只做到 body 级别，未到 references 级 |
| 问答集测试仅为 5 条预设 case | 非随机采样，不覆盖真实用户分布 |
