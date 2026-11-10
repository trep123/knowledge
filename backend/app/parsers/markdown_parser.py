"""Markdown 解析：保留原文（标题/代码块结构由切片器保留），提取纯文本视图。"""
from markdown_it import MarkdownIt


def parse_markdown(file_path: str) -> tuple[list[tuple[int, str]], int]:
    with open(file_path, encoding="utf-8", errors="replace") as f:
        raw = f.read()
    text = MarkdownIt().render(raw)
    # render 输出 HTML，这里保留原始 Markdown 更利于切片结构，直接返回原文
    return [(1, raw)], 1
