"""按文件类型分发解析器，统一返回 [(page_number, text), ...]。"""
from pathlib import Path


def parse_document(file_path: str, file_type: str) -> tuple[list[tuple[int, str]], int]:
    ext = file_type.lower().lstrip(".")
    if ext == "pdf":
        from app.parsers.pdf_parser import parse_pdf

        return parse_pdf(file_path)
    if ext == "docx":
        from app.parsers.docx_parser import parse_docx

        return parse_docx(file_path)
    if ext in ("md", "markdown"):
        from app.parsers.markdown_parser import parse_markdown

        return parse_markdown(file_path)
    if ext == "txt":
        from app.parsers.txt_parser import parse_txt

        return parse_txt(file_path)
    if ext in ("png", "jpg", "jpeg", "tiff", "tif"):
        from app.parsers.image_parser import parse_image

        return parse_image(file_path)
    raise ValueError(f"不支持的文件类型: {ext}（原始文件名: {Path(file_path).name}）")
