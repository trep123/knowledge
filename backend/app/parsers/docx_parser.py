"""DOCX 解析：段落 + 表格，按文档顺序输出。"""
import docx


def parse_docx(file_path: str) -> tuple[list[tuple[int, str]], int]:
    document = docx.Document(file_path)
    parts: list[str] = []
    for para in document.paragraphs:
        text = para.text.strip()
        if text:
            parts.append(text)
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            if any(cells):
                parts.append(" | ".join(cells))
    full_text = "\n\n".join(parts)
    return [(1, full_text)], 1
