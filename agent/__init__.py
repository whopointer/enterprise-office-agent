"""Agent 会话和字段抽取能力。

避免在包初始化时导入 conversation，防止 llm 路由导入字段抽取时形成循环依赖。
需要多轮会话时请直接导入 `agent.conversation`。
"""

from .field_extractor import extract_fields_from_query

__all__ = [
    "extract_fields_from_query",
]
