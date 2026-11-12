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


ALLOWED_HISTORY_ROLES = ("user", "assistant")


def sanitize_history(
    history: list[dict] | None,
    query: str | None = None,
    max_messages: int | None = None,
    max_chars: int | None = None,
) -> list[dict]:
    """清洗客户端传入的对话历史。

    - 只保留 user / assistant 消息，丢弃 system 等角色（防止覆盖系统提示词）
    - 只保留字符串内容，且只传 role/content 两个字段
    - 末尾与当前问题相同的 user 消息去掉，避免重复
    - 从最近的消息往前保留，受条数与总字符数限制（防止撑爆上下文）
    """
    from app.config import settings

    max_messages = settings.history_max_messages if max_messages is None else max_messages
    max_chars = settings.history_max_chars if max_chars is None else max_chars
    cleaned = [
        {"role": m.get("role"), "content": m.get("content")}
        for m in (history or [])
        if isinstance(m, dict) and m.get("role") in ALLOWED_HISTORY_ROLES and isinstance(m.get("content"), str)
    ]
    if cleaned and query is not None and cleaned[-1]["role"] == "user" and cleaned[-1]["content"] == query:
        cleaned.pop()

    kept: list[dict] = []
    budget = max_chars
    for m in reversed(cleaned[-max_messages:] if max_messages else []):
        if len(m["content"]) > budget:
            break
        kept.append(m)
        budget -= len(m["content"])
    kept.reverse()
    # 历史以 assistant 开头没有意义，去掉开头的孤立 assistant
    while kept and kept[0]["role"] != "user":
        kept.pop(0)
    return kept


def build_messages(query: str, chunks: list[dict], history: list[dict] | None = None) -> list[dict]:
    context = build_context(chunks)
    user_content = f"知识库资料：\n{context}\n\n问题：{query}"
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(sanitize_history(history, query))
    messages.append({"role": "user", "content": user_content})
    return messages
