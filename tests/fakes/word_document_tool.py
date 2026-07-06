"""测试专用 Word 文档工具 fake。"""

from __future__ import annotations

from typing import Any

from _skill.models import SkillDefinition
from tools import WordDocumentTool


class TestWordDocumentTool:
    """包装真实 Word 工具，便于测试中断言 skill 信息。"""

    name = "TestWordDocument"

    def execute(self, prompt: str, *, skill: SkillDefinition, context: dict[str, Any]) -> dict[str, Any]:
        """根据测试字段生成 docx 文件并返回产物路径。"""
        fields = context.get("fields", {})
        result = WordDocumentTool().run(fields=fields, content=prompt, default_title=skill.name)
        return {**result, "skill_name": skill.name}
