"""递归切片器。

计量单位：字符数（全系统统一，不与 token 混用）。
尽量沿段落 / 换行 / 中英文句末标点切分，保留结构。
"""
import re

SEPARATORS = ["\n\n", "\n", "。", "！", "？", "；", ". ", "! ", "? ", "; ", " ", ""]


def _split_by(text: str, sep: str) -> list[str]:
    if sep == "":
        return list(text)
    parts = text.split(sep)
    return [p + sep for p in parts[:-1] if p] + ([parts[-1]] if parts[-1] else [])


def _merge_pieces(pieces: list[str], chunk_size: int, overlap: int) -> list[str]:
    chunks: list[str] = []
    buf = ""
    for piece in pieces:
        if len(piece) > chunk_size:
            if buf:
                chunks.append(buf)
                buf = ""
            chunks.extend(_merge_pieces(_split_by(piece, ""), chunk_size, overlap))
            continue
        if buf and len(buf) + len(piece) > chunk_size:
            chunks.append(buf)
            buf = buf[-overlap:] if overlap else ""
        buf += piece
    if buf.strip():
        chunks.append(buf)
    return chunks


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 120) -> list[str]:
    text = re.sub(r"[ \t]+", " ", text)
    pieces: list[str] = []
    for para in _split_by(text, "\n\n"):
        pieces.extend(_split_by(para, "\n"))
    result = []
    for c in _merge_pieces(pieces, chunk_size, overlap):
        c = c.strip()
        if len(c) >= 20:  # 丢弃过短碎片
            result.append(c)
    return result


def clean_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
