"""Skill 系统测试共享夹具 — 对齐官方 SKILL.md 格式（name + description + allowed-tools + body）。"""

from __future__ import annotations

from pathlib import Path
import shutil


def write_skill(root: Path, name: str, frontmatter: str, body: str) -> Path:
    """写入一个 SKILL.md 到指定目录。"""
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(f"---\n{frontmatter.strip()}\n---\n{body.strip()}\n", encoding="utf-8")
    return skill_file


def build_pipeline_test_skills(tmp_path: Path) -> Path:
    """构造 4 个符合官方格式的 skill，覆盖不同特征。

    - document-generator : 文档生成（有 allowed-tools）
    - code-reviewer       : 代码审查（无 allowed-tools，默认空）
    - simple-echo         : 最简 skill（回显）
    - data-analyzer       : 数据分析（有 license + compatibility）
    """
    skills_dir = tmp_path / "skills"

    write_skill(
        skills_dir,
        "document-generator",
        """
name: document-generator
description: 生成 Word 文档报告，根据指定模板填充内容并输出 docx 文件。触发条件：用户要求生成文档、报告、合同、证书等。
allowed-tools: [Read, Bash, Write]
""",
        "# Document Generator\n\n根据指定模板和字段生成 Word 报告。\n\n## 使用流程\n1. 确认用户需要的文件名和标题\n2. 读取 assets/report-template.docx 作为模板\n3. 运行 scripts/generate.py 生成文档",
    )

    write_skill(
        skills_dir,
        "code-reviewer",
        """
name: code-reviewer
description: 对指定代码项目执行代码审查，检查常见问题并生成审查报告。支持 Python、JavaScript、Go 等语言。
""",
        "# Code Reviewer\n\n对代码项目执行审查，输出问题列表和修复建议。\n\n## 使用流程\n1. 确认审查范围（目录或文件路径）\n2. 读取代码文件\n3. 输出 markdown 格式的审查报告",
    )

    write_skill(
        skills_dir,
        "simple-echo",
        """
name: simple-echo
description: 回显用户输入，用于验证基础 skill 路由和执行管线是否正常。触发条件：用户发送 ping、echo、测试连通性等请求。
allowed-tools: []
""",
        "# Simple Echo\n\n回显用户输入内容。",
    )

    write_skill(
        skills_dir,
        "data-analyzer",
        """
name: data-analyzer
description: 分析 CSV 或 JSON 数据文件，生成统计摘要和可视化图表。触发条件：用户上传数据文件或要求进行数据分析。
allowed-tools: [Read, Bash, Write]
license: MIT
compatibility: python>=3.10
""",
        "# Data Analyzer\n\n读取数据文件，计算统计指标并生成图表。\n\n## 使用流程\n1. 读取用户指定的数据文件\n2. 运行 scripts/analyze.py 进行分析\n3. 输出分析报告",
    )

    return skills_dir


# 从真实 skills/ 复制子集用于 LLM 路由测试
LLM_TEST_SKILL_NAMES = [
    "word-report-generator-1.0.0",
    "pdf",
    "security-best-practices",
    "strict-trigger-lab",
    "render-deploy",
]


def build_llm_test_skills(tmp_path: Path) -> Path:
    """从真实 skills/ 目录复制一组 skill 到临时目录用于 LLM 测试。"""
    repo_root = Path(__file__).resolve().parents[1]
    source_skills_dir = repo_root / "skills"
    target_skills_dir = tmp_path / "skills"
    target_skills_dir.mkdir(parents=True, exist_ok=True)

    for name in LLM_TEST_SKILL_NAMES:
        src = source_skills_dir / name
        dst = target_skills_dir / name
        if src.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)

    return target_skills_dir
