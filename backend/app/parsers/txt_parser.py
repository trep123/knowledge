def parse_txt(file_path: str) -> tuple[list[tuple[int, str]], int]:
    with open(file_path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    return [(1, text)], 1
