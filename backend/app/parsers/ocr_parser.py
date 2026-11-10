"""OCR 封装：pytesseract，中英文混合识别。"""
import io

import pytesseract
from PIL import Image

TESSERACT_LANG = "chi_sim+eng"


def ocr_image_bytes(image_bytes: bytes) -> str:
    img = Image.open(io.BytesIO(image_bytes))
    return pytesseract.image_to_string(img, lang=TESSERACT_LANG)


def ocr_pil_image(img: Image.Image) -> str:
    return pytesseract.image_to_string(img, lang=TESSERACT_LANG)
