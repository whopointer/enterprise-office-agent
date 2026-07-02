"""Skill 系统测试共享夹具。"""

from __future__ import annotations

from pathlib import Path


def write_skill(root: Path, name: str, frontmatter: str, body: str) -> Path:
    """写入一个测试用 SKILL.md。"""
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(f"---\n{frontmatter.strip()}\n---\n{body.strip()}\n", encoding="utf-8")
    return skill_file


def build_design_skills(tmp_path: Path) -> Path:
    """构造 design.md 要求的测试 skill 清单。"""
    skills_dir = tmp_path / "skills"

    write_skill(
        skills_dir,
        "mockskill",
        """
name: mockskill
description: 基础 mock skill，用于 token 基线对比
triggers:
  keywords: [mock, 基线]
metrics:
  expected_skill: mockskill
  expected_activation: true
token_estimate:
  system_prompt: 10
  per_reference: 0
  per_asset: 0
""",
        "# Mock\n基础能力。",
    )

    write_skill(
        skills_dir,
        "word-generator",
        """
name: word-generator
description: 生成 Word 文档报告，支持 docx 模板填充
triggers:
  keywords: [word, docx, 报告]
  patterns: [生成.*报告]
assets:
  - path: assets/template.docx
    type: word_document
    description: 报告模板
metrics:
  expected_skill: word-generator
  expected_activation: true
  expected_assets: [assets/template.docx]
token_estimate:
  system_prompt: 100
  per_reference: 0
  per_asset: 30
""",
        "# Word Generator\n根据模板生成 Word 报告。",
    )
    asset_dir = skills_dir / "word-generator" / "assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    (asset_dir / "template.docx").write_bytes(b"fake docx template")

    write_skill(
        skills_dir,
        "redline-demo",
        """
name: redline-demo
description: 红线规则测试，缺少 filename 或 template_name 时必须拒绝激活
triggers:
  keywords: [红线, redline]
red_lines:
  - field: filename
    message: 缺少文件名参数
  - field: template_name
    message: 未指定模板
metrics:
  expected_skill: redline-demo
  expected_activation: true
token_estimate:
  system_prompt: 80
  per_reference: 0
  per_asset: 0
""",
        "# Redline Demo\n只有红线字段齐全才允许执行。",
    )

    write_skill(
        skills_dir,
        "skill-search",
        """
name: skill-search
description: 搜寻所有已注册 skill，并引用 mockskill 验证 reference 展开
triggers:
  keywords: [搜索skill, skill_search, 注册]
references:
  - mockskill
metrics:
  expected_skill: skill-search
  expected_activation: true
  expected_references: [mockskill]
token_estimate:
  system_prompt: 120
  per_reference: 40
  per_asset: 0
""",
        "# Skill Search\n列出所有已注册 skill。",
    )

    return skills_dir
