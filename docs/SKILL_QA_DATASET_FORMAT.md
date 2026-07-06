# Skill 问答集格式规范

## 1. 文件格式

问答集使用 JSONL 格式：一行一个 JSON object。

建议路径：

```text
datasets/skill_qa.jsonl
```

设计原则：

- 所有 skill 使用同一套字段结构。
- 不同 skill 只改变字段值，不改变 schema。
- 测试脚本逐行读取 JSONL，根据 `expected_skill`、`must_include`、`forbidden`、`artifact_expectation` 等字段完成自动评分。

## 2. 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | 是 | 用例唯一编号 |
| `category` | string | 是 | 用例分类，如 `document_generation`、`deployment` |
| `turns` | list[string] | 是 | 用户输入。单轮时只有一个元素，多轮时按顺序写入多条 |
| `expected_skill` | string / null | 是 | 期望命中的 skill name，必须使用 `SKILL.md` 中的 `name` |
| `expected_activation` | boolean | 是 | 是否期望激活 skill |
| `expected_fields` | object | 否 | 期望抽取出的结构化字段 |
| `must_include` | list[string] | 否 | 输出中必须包含的关键词或要点 |
| `should_include` | list[string] | 否 | 输出中建议包含的关键词或要点 |
| `forbidden` | list[string] | 否 | 输出中不应出现的内容，用于检测串 skill 或明显幻觉 |
| `ordered_steps` | list[string/object] | 否 | 期望答案中按顺序出现的步骤，用于判断步骤顺序是否合理 |
| `technical_checks` | list[object] | 否 | 技术正确性断言：必须包含、至少包含其一、禁止包含、正则匹配 |
| `config_checks` | list[object] | 否 | 配置可执行性检查，如 render.yaml 是否可解析、字段是否完整 |
| `document_standard` | object | 否 | 产物文档/方案文档标准，如最少章节数、最少字符数、必备章节 |
| `allowed_references` | list[string] | 否 | 允许引用的 reference / asset / script 路径 |
| `artifact_expectation` | object | 否 | 是否期望产生产物，如 docx |
| `judge_rubric` | object | 否 | LLM-as-judge 或人工复核的评分说明，覆盖技术正确性、步骤顺序、配置可执行性、问题解决度、隐蔽严重错误、文档标准 |
| `quality_thresholds` | object | 否 | 单条 case 的通过阈值，如 `local_score`、`judge_score`、`critical_error_score` 和分项阈值 |
| `weights` | object | 否 | 单条 case 的评分权重 |
| `notes` | string | 否 | 备注 |

## 3. 空模板

只包含字段，不填业务数据：

```json
{
  "id": "",
  "category": "",
  "turns": [],
  "expected_skill": null,
  "expected_activation": true,
  "expected_fields": {},
  "must_include": [],
  "should_include": [],
  "forbidden": [],
  "ordered_steps": [],
  "technical_checks": [],
  "config_checks": [],
  "document_standard": {
    "min_sections": 0,
    "min_chars": 0,
    "required_sections_any": []
  },
  "allowed_references": [],
  "artifact_expectation": {
    "type": null,
    "required": false,
    "path_field": null,
    "checks": []
  },
  "judge_rubric": {
    "technical_correctness": "",
    "step_order": "",
    "config_executability": "",
    "problem_resolution": "",
    "hidden_critical_errors": "",
    "document_standard": ""
  },
  "quality_thresholds": {
    "local_score": 0,
    "judge_score": 0,
    "critical_error_score": 0,
    "components": {}
  },
  "weights": {
    "routing": 0,
    "structure": 0,
    "groundedness": 0,
    "field_extraction": 0,
    "language": 0,
    "efficiency": 0
  },
  "notes": ""
}
```

## 4. 带数据示例

下面是同一 schema 下的真实示例。注意 `expected_skill` 使用的是 `SKILL.md` 里的 `name`，不是目录名。

```json
{
  "id": "QA-DOCX-001",
  "category": "document_generation",
  "turns": [
    "帮我生成一份项目周报 Word 报告，文件名 weekly-report.docx"
  ],
  "expected_skill": "docx-report-generator",
  "expected_activation": true,
  "expected_fields": {
    "filename": "weekly-report.docx"
  },
  "must_include": [
    "项目周报",
    "本周进展",
    "问题风险",
    "下周计划",
    "weekly-report.docx"
  ],
  "should_include": [
    "标题",
    "日期",
    "表格",
    "目录"
  ],
  "forbidden": [
    "render.yaml",
    "Render",
    "部署"
  ],
  "allowed_references": [
    "references/template-syntax.md",
    "references/report-config.md",
    "scripts/docx_ops.py"
  ],
  "artifact_expectation": {
    "type": "docx",
    "required": false,
    "path_field": "filename",
    "checks": [
      "file_exists",
      "readable_docx",
      "contains_title"
    ]
  },
  "judge_rubric": {
    "structure": "是否包含项目周报的必要结构：标题、本周进展、问题风险、下周计划。",
    "skill_fit": "是否围绕 Word 报告生成，而不是泛泛给写作建议。",
    "groundedness": "是否只引用 docx-report-generator 中真实存在的能力、reference 或脚本。",
    "language": "中文输入应主要使用中文输出。",
    "risk_handling": "缺少业务数据时，应说明需要补充哪些内容，或给出可执行的默认结构。"
  },
  "weights": {
    "routing": 0.25,
    "structure": 0.25,
    "groundedness": 0.2,
    "field_extraction": 0.1,
    "language": 0.1,
    "efficiency": 0.1
  },
  "notes": "文档生成 skill 示例。若执行 adapter 只是 LLM 文本生成，则 artifact_expectation.required 应保持 false。"
}
```

## 5. JSONL 示例

实际 `datasets/skill_qa.jsonl` 中应写成单行：

```jsonl
{"id":"QA-DOCX-001","category":"document_generation","turns":["帮我生成一份项目周报 Word 报告，文件名 weekly-report.docx"],"expected_skill":"docx-report-generator","expected_activation":true,"expected_fields":{"filename":"weekly-report.docx"},"must_include":["项目周报","本周进展","问题风险","下周计划","weekly-report.docx"],"should_include":["标题","日期","表格","目录"],"forbidden":["render.yaml","Render","部署"],"allowed_references":["references/template-syntax.md","references/report-config.md","scripts/docx_ops.py"],"artifact_expectation":{"type":"docx","required":false,"path_field":"filename","checks":["file_exists","readable_docx","contains_title"]},"judge_rubric":{"structure":"是否包含项目周报的必要结构：标题、本周进展、问题风险、下周计划。","skill_fit":"是否围绕 Word 报告生成，而不是泛泛给写作建议。","groundedness":"是否只引用 docx-report-generator 中真实存在的能力、reference 或脚本。","language":"中文输入应主要使用中文输出。","risk_handling":"缺少业务数据时，应说明需要补充哪些内容，或给出可执行的默认结构。"},"weights":{"routing":0.25,"structure":0.25,"groundedness":0.2,"field_extraction":0.1,"language":0.1,"efficiency":0.1},"notes":"文档生成 skill 示例。若执行 adapter 只是 LLM 文本生成，则 artifact_expectation.required 应保持 false。"}
```

## 6. 答案正确性判定口径

问答测试不做标准答案全文比对，而是同时使用本地确定性检查和 LLM-as-judge：

- `must_include` / `should_include`：检查关键要点覆盖率。
- `forbidden`：拦截串 skill、明显幻觉和严重错误表述。
- `ordered_steps`：检查步骤是否按合理顺序出现。
- `technical_checks`：检查技术断言是否满足，例如必须提到 `PORT`、不得硬编码密钥。
- `config_checks`：解析配置代码块，例如校验 `render.yaml` 是否可解析且字段完整。
- `document_standard`：检查输出是否具备可交付文档结构。
- 幻觉引用检查：答案提到的 `scripts/`、`references/`、`assets/` 路径必须真实存在。
- LLM-as-judge：评分 `technical_correctness`、`step_order`、`config_executability`、`problem_resolution`、`hidden_critical_errors`、`document_standard` 和 `overall`。

LLM judge 输出中的 `critical_issues` 只放足以判定失败的严重问题；普通缺陷或改进项应放入 `warnings`。如果 judge 把普通风险误放进 `critical_issues`，但 `hidden_critical_errors` 达到 `critical_error_score`，测试脚本会把它降级为 warning。
