"""WordDocumentTool 契约测试。"""

from __future__ import annotations

from pathlib import Path

from docx import Document

from tools import WordDocumentTool


def _docx_text(path: Path) -> str:
    document = Document(path)
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def test_word_document_tool_generates_readable_docx(tmp_path: Path) -> None:
    """工具应生成可读 docx，并写入标题和正文。"""
    output_path = tmp_path / "report.docx"

    result = WordDocumentTool().run(
        fields={"output_path": str(output_path), "title": "测试报告", "content": "正文内容"},
        default_title="默认标题",
    )

    assert result["output_path"] == str(output_path)
    assert output_path.exists()
    text = _docx_text(output_path)
    assert "测试报告" in text
    assert "正文内容" in text


def test_word_document_tool_uses_default_filename(tmp_path: Path, monkeypatch) -> None:
    """未指定路径时，应在当前目录生成默认文件名。"""
    monkeypatch.chdir(tmp_path)

    result = WordDocumentTool().run(fields={"title": "默认文件名"}, content="默认正文")

    output_path = tmp_path / "skill-output.docx"
    assert result["output_path"] == str(output_path)
    assert output_path.exists()
    assert "默认文件名" in _docx_text(output_path)


def test_word_document_tool_relative_path_is_cwd_relative(tmp_path: Path, monkeypatch) -> None:
    """相对路径应相对当前工作目录生成。"""
    monkeypatch.chdir(tmp_path)

    result = WordDocumentTool().run(fields={"output_path": "nested/out.docx"}, content="正文")

    output_path = tmp_path / "nested" / "out.docx"
    assert result["output_path"] == str(output_path)
    assert output_path.exists()
