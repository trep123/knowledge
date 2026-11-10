"""PDF 解析：PyMuPDF 文本提取；文本稀疏页自动降级为 OCR（扫描版 PDF）。"""
import fitz

from app.parsers.ocr_parser import ocr_pil_image


def parse_pdf(file_path: str) -> tuple[list[tuple[int, str]], int]:
    """返回 ([(page_number, text), ...], page_count)。"""
    from PIL import Image
    import io

    pages: list[tuple[int, str]] = []
    doc = fitz.open(file_path)
    for page_index in range(len(doc)):
        page = doc[page_index]
        text = page.get_text("text").strip()
        if len(text) < 50:  # 可能是扫描页
            pix = page.get_pixmap(dpi=200)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            ocr_text = ocr_pil_image(img).strip()
            if ocr_text:
                text = ocr_text
        pages.append((page_index + 1, text))
    page_count = len(doc)
    doc.close()
    return pages, page_count
