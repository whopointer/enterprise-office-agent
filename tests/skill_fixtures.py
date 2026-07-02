"""Skill 系统测试共享夹具。提供两组 skill：

1. `build_pipeline_test_skills` — 带完整 DSL（triggers / red_lines / references / assets），
   用于测试 Discovery / Activation / Execution / Metrics 等本地 pipeline 阶段。
2. `build_llm_test_skills` — 从真实 skills/ 目录子集的副本构造，用于 LLM 路由测试。
"""

from __future__ import annotations

from pathlib import Path
import shutil


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def write_skill(root: Path, name: str, frontmatter: str, body: str) -> Path:
    """写入一个 SKILL.md 到指定目录。"""
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(f"---\n{frontmatter.strip()}\n---\n{body.strip()}\n", encoding="utf-8")
    return skill_file


# ---------------------------------------------------------------------------
# 夹具 A：带完整 DSL schema 的测试 skill（pipeline 阶段测试用）
# ---------------------------------------------------------------------------

def build_pipeline_test_skills(tmp_path: Path) -> Path:
    """构造 5 个具备完整 YAML DSL 的 skill，模拟真实 agent 能力。

    技能清单：
    - document-generator   : Word 文档生成，2 个红线字段 + 1 个 asset
    - skill-index          : 搜寻已注册 skill，1 个 reference
    - security-auditor     : 安全检查，3 个红线字段（多轮会话测试用）
    - simple-echo          : 最简 skill，无红线和引用（基线用）
    - pattern-matcher      : 用正则 pattern 而非关键词触发
    """
    skills_dir = tmp_path / "skills"

    # --- document-generator ---
    write_skill(
        skills_dir,
        "document-generator",
        """
name: document-generator
description: 生成 Word 文档报告，根据指定模板填充内容并输出 docx 文件
triggers:
  keywords: [word, docx, document, 文档, 报告, 生成报告]
  patterns: ["生成.*(?:报告|文档|docx|word)"]
red_lines:
  - field: filename
    message: 缺少输出文件名参数
  - field: title
    message: 缺少报告标题
references: []
assets:
  - path: assets/report-template.docx
    type: word_document
    description: 默认报告模板
metrics:
  expected_skill: document-generator
  expected_activation: true
  expected_assets: [assets/report-template.docx]
token_estimate:
  system_prompt: 120
  per_reference: 0
  per_asset: 40
""",
        "# Document Generator\n根据指定模板和字段生成 Word 报告。",
    )
    asset_dir = skills_dir / "document-generator" / "assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    (asset_dir / "report-template.docx").write_bytes(b"binary docx template content")

    # --- skill-index ---
    write_skill(
        skills_dir,
        "skill-index",
        """
name: skill-index
description: 扫描并列出当前系统中所有已注册的 skill，支持关键词过滤
triggers:
  keywords: [skill, 技能, 搜索skill, 列出skill, skill列表, 注册列表]
  patterns: ["搜索.*skill", "列出.*skill", "查看.*技能"]
red_lines: []
references:
  - document-generator
assets: []
metrics:
  expected_skill: skill-index
  expected_activation: true
  expected_references: [document-generator]
token_estimate:
  system_prompt: 100
  per_reference: 50
  per_asset: 0
""",
        "# Skill Index\n列出所有已注册 skill，并引用 document-generator 作为示例。",
    )

    # --- security-auditor ---
    write_skill(
        skills_dir,
        "security-auditor",
        """
name: security-auditor
description: 对指定代码项目执行安全审查，检查常见漏洞并生成审计报告
triggers:
  keywords: [security, audit, 安全, 审计, 漏洞, 安全检查, 代码审查]
  patterns: ["安全.*(?:审查|审计|检查|扫描)"]
red_lines:
  - field: scope
    message: 缺少审查范围（目录或文件路径）
  - field: language
    message: 缺少目标编程语言
  - field: output_format
    message: 缺少输出格式（markdown/json/html）
references: []
assets: []
metrics:
  expected_skill: security-auditor
  expected_activation: true
token_estimate:
  system_prompt: 150
  per_reference: 0
  per_asset: 0
""",
        "# Security Auditor\n对代码项目执行安全审查，输出漏洞列表和修复建议。",
    )

    # --- simple-echo ---
    write_skill(
        skills_dir,
        "simple-echo",
        """
name: simple-echo
description: 回显用户输入，用于验证基础 skill 路由和执行管线是否正常
triggers:
  keywords: [echo, 回显, ping, 测试echo]
  patterns: ["echo.*test", "回显.*测试"]
red_lines: []
references: []
assets: []
metrics:
  expected_skill: simple-echo
  expected_activation: true
token_estimate:
  system_prompt: 10
  per_reference: 0
  per_asset: 0
""",
        "# Simple Echo\n回显用户输入内容。",
    )

    # --- pattern-matcher ---
    write_skill(
        skills_dir,
        "pattern-matcher",
        """
name: pattern-matcher
description: 演示纯正则模式匹配，不依赖关键词，只用 pattern 触发
triggers:
  keywords: []
  patterns: ["创建.*表格", "生成.*表格", "绘制.*图表"]
red_lines: []
references: []
assets: []
metrics:
  expected_skill: pattern-matcher
  expected_activation: true
token_estimate:
  system_prompt: 50
  per_reference: 0
  per_asset: 0
""",
        "# Pattern Matcher\n使用正则模式匹配用户意图。",
    )

    return skills_dir


# ---------------------------------------------------------------------------
# 夹具 B：从真实 skills/ 复制子集（LLM 路由测试用）
# ---------------------------------------------------------------------------

# 选择了 5 个具有不同特征的 skill：有 references、有 assets、有触发描述、无触发描述
LLM_TEST_SKILL_NAMES = [
    "word-report-generator-1.0.0",   # 文档生成，有 references
    "pdf",                            # PDF 处理，有 assets，无 references
    "security-best-practices",        # 安全审查，大量 references，有严格 trigger 条件
    "strict-trigger-lab",             # 严格条件触发，用于测试拒绝场景
    "render-deploy",                  # 部署，大量 assets
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
