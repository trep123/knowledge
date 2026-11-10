"""图片解析：PNG/JPG/JPEG/TIFF 直接 OCR。"""
from app.parsers.ocr_parser import ocr_image_bytes


def parse_image(file_path: str) -> tuple[list[tuple[int, str]], int]:
    with open(file_path, "rb") as f:
        data = f.read()
    text = ocr_image_bytes(data)
    return [(1, text)], 1
