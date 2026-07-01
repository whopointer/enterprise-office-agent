# 报告配置格式

`create-report` 命令的配置JSON格式:

```json
{
  "sections": [
    {
      "type": "heading",
      "content": "项目概述",
      "level": 1
    },
    {
      "type": "text",
      "content": "本项目旨在..."
    },
    {
      "type": "table",
      "headers": ["指标", "Q1", "Q2", "Q3", "Q4"],
      "rows": [
        ["营收", "100万", "120万", "150万", "180万"],
        ["利润", "20万", "25万", "35万", "45万"]
      ]
    },
    {
      "type": "bullet",
      "items": [
        "第一项要点",
        "第二项要点",
        "第三项要点"
      ]
    }
  ]
}
```

## section类型

| type | 必填字段 | 说明 |
|------|----------|------|
| `heading` | content, level | 标题(1-4级) |
| `text` | content | 正文段落 |
| `table` | headers, rows | 表格 |
| `bullet` | items | 无序列表 |
