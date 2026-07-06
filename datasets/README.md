# Skill 测试数据集

本目录统一存放 Skill 系统自动化测试和评测脚本使用的数据集。

## 文件说明

| 文件 | 用途 | 用例数 | 说明 |
|------|------|--------|------|
| `skill_routing_eval.jsonl` | 大样本路由评测 | 120 | 覆盖文档生成、部署、其他 skill、负例、模糊意图、否定干扰和字段噪声 |
| `render-deploy-qa.json` | QA 问答集测试 | 20 | Render 部署 skill 的真实输出质量评测 |

## 路由评测 JSONL 格式

`skill_routing_eval.jsonl` 每行是一条 JSON：

```json
{
  "id": "ROUTE-001",
  "query": "用户自然语言输入",
  "expected_skill": "docx-report-generator",
  "expected_activation": true,
  "category": "document_generation",
  "difficulty": "easy",
  "tags": ["tp"]
}
```

## QA JSON 格式

```json
{
  "id": "QA-01",
  "query": "用户自然语言输入",
  "expected_skill": "render-deploy | null",
  "expected_activation": true,
  "must_include": ["必须命中的关键要素"],
  "should_include": ["建议命中的要素"],
  "forbidden": ["禁止出现的严重错误或串 skill 内容"],
  "ordered_steps": [{"any": ["前提", "准备"]}, {"any": ["配置"]}, {"any": ["验证"]}],
  "technical_checks": [
    {
      "id": "port",
      "must_include": ["PORT"],
      "must_not_include": ["固定 3000"]
    }
  ],
  "config_checks": [
    {
      "id": "render_yaml_shape",
      "type": "render_yaml",
      "required": false,
      "required_service_fields": ["type", "name"]
    }
  ],
  "document_standard": {
    "min_sections": 3,
    "min_chars": 200,
    "required_sections_any": [["前提"], ["配置"], ["验证"]]
  },
  "judge_rubric": {
    "technical_correctness": "技术是否真实正确",
    "step_order": "步骤顺序是否合理",
    "config_executability": "配置是否可执行",
    "problem_resolution": "是否解决用户具体问题",
    "hidden_critical_errors": "是否存在隐蔽严重错误",
    "document_standard": "产物/方案文档是否标准"
  },
  "quality_thresholds": {
    "local_score": 0.65,
    "judge_score": 0.70,
    "critical_error_score": 0.80
  },
  "difficulty": "simple | medium | hard",
  "description": "场景说明"
}
```

## 用例设计原则

### 路由评测

1. 覆盖明确正例、明确负例、模糊表达和否定干扰。
2. 覆盖多个真实 skill，而不是只覆盖文档生成和 Render。
3. 按 category 和 difficulty 分层，便于定位边界问题。

### QA 问答集

1. **覆盖全场景**：简单入门 / 多服务复杂部署 / Docker 路径 / 故障排查 / 前提条件 / 部署后验证
2. **覆盖全服务类型**：web / worker / cron / static / pserv
3. **覆盖全运行时**：node / python / go / ruby / static
4. **包含阴性对照**：无关请求应返回 should_call=false
5. **难度分层**：simple 8 条 / medium 9 条 / hard 2 条
6. **答案质量可量化**：每条列出必须命中的要素、步骤顺序、技术断言、配置检查、文档标准和 judge rubric
7. **严格错误拦截**：通过 `forbidden`、`technical_checks.must_not_include` 和 LLM-as-judge 的 `hidden_critical_errors` 检测隐蔽严重错误
8. **配置可执行性**：涉及 `render.yaml` 的 case 用 `config_checks` 校验 YAML 代码块是否可解析、是否包含 `services`、服务字段是否完整
9. **失败原因可诊断**：报告区分 `routing`、`missed_activation`、`local_quality`、`judge_quality`、`critical_issue`、`language`、`route_invalid` 等失败原因
10. **严重问题与普通风险分离**：LLM judge 的 `critical_issues` 代表足以失败的问题，普通缺陷进入 `warnings`

## 使用方法

```bash
# 运行 120 条真实 LLM 路由评测
python3 scripts/run_routing_eval.py --output-dir test-results

# 运行全部问答集测试
python3 -m pytest tests/test_skill_qa.py -v
```

问答集测试会输出 `test-results/qa-report.md` 和 `test-results/qa-report.json`。报告中的 `total_cases` 会统计已进入评测记录的样本；供应商不可用、路由返回格式异常、judge 不可用等情况也会作为 skipped case 写入明细，避免样本静默丢失。
