SYSTEM_PROMPT = (
    "你是本地知识库问答助手。只能根据用户提供的知识库资料回答问题。\n"
    "要求：\n"
    "1. 严格依据资料内容作答，不得编造资料中不存在的信息。\n"
    "2. 如果资料不足以回答问题，明确说明“知识库中未找到足够依据”。\n"
    "3. 回答使用与问题相同的语言。\n"
    "4. 不要在回答中自行列出参考资料编号，系统会自动附加引用。"
)


def build_context(chunks: list[dict]) -> str:
    """将检索到的切片构建为带编号的上下文。chunks 元素需含 filename/page_number/content。"""
    parts = []
    for i, c in enumerate(chunks, start=1):
        page = c.get("page_number")
        loc = f"文件: {c.get('filename', '未知')} 第{page}页" if page else f"文件: {c.get('filename', '未知')}"
        parts.append(f"[资料{i}] {loc}\n{c['content']}")
    return "\n\n".join(parts)


def build_messages(query: str, chunks: list[dict], history: list[dict] | None = None) -> list[dict]:
    context = build_context(chunks)
    user_content = f"知识库资料：\n{context}\n\n问题：{query}"
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history[:-1] if history and history[-1].get("role") == "user" else history)
    messages.append({"role": "user", "content": user_content})
    return messages
