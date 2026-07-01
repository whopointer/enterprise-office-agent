---
name: docx-report-generator
description: "Word报告自动生成神器。自动生成专业Word文档报告，支持模板填充、目录生成、表格/图表插入、页眉页脚、多级标题、样式主题、批量邮件合并。当用户需要生成Word报告、创建合同文档、批量生成通知/证书、填充Word模板、制作商业计划书时触发。"
---

# DOCX Report Generator

Word文档报告自动生成工具，从模板到成品一站式搞定。

## 核心能力

1. **模板填充** - 用数据自动填充Word模板中的占位符
2. **从头创建** - 用代码生成完整的专业报告文档
3. **邮件合并** - 批量生成个性化文档（通知、证书、合同）
4. **目录生成** - 自动根据标题层级生成目录
5. **表格插入** - 创建格式化表格，支持合并单元格
6. **图表插入** - 在文档中嵌入数据图表
7. **样式主题** - 自定义文档样式和配色方案
8. **批量输出** - 批量生成、批量导出PDF

## 快速开始

### 从模板填充

```bash
python3 scripts/docx_ops.py fill-template template.docx --data data.json -o report.docx
```

### 创建报告

```bash
python3 scripts/docx_ops.py create-report --title "月度销售报告" --config report_config.json -o report.docx
```

### 批量邮件合并

```bash
python3 scripts/docx_ops.py mail-merge template.docx --data recipients.csv -o output/
```

### 添加目录

```bash
python3 scripts/docx_ops.py add-toc report.docx -o report_with_toc.docx
```

### 导出PDF

```bash
python3 scripts/docx_ops.py to-pdf report.docx -o report.pdf
```

## 模板语法

模板中使用 `{{变量名}}` 作为占位符，支持:

- `{{公司名称}}` - 简单文本替换
- `{{#表格}}...{{/表格}}` - 循环生成行
- `{{日期:format=YYYY-MM-DD}}` - 格式化日期

详见 [references/template-syntax.md](references/template-syntax.md)

## 依赖安装

```bash
pip install python-docx jinja2 pandas
# 导出PDF需要: sudo apt install libreoffice
```

## 报告配置

创建报告的配置JSON格式见 [references/report-config.md](references/report-config.md)
