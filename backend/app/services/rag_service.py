"""RAG 问答服务：检索 -> 上下文构建 -> 本地 LLM -> 回答 + 引用。

REST、OpenAI 兼容 API、Web 问答共用本服务。
"""
import logging
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass

from app.config import settings
from app.models import KnowledgeBase
from app.rag.context_builder import build_messages
from app.services import llm_service
from app.services.retrieval_service import hybrid_search


@dataclass
class Citation:
    document_id: str
    filename: str
    page_number: int | None
    chunk_id: str
    content: str
    score: float

    def to_dict(self) -> dict:
        return {
            "document_id": self.document_id,
            "filename": self.filename,
            "page_number": self.page_number,
            "chunk_id": self.chunk_id,
            "content": self.content[:500],
            "score": round(self.score, 4),
        }


logger = logging.getLogger(__name__)

STREAM_ERROR_MESSAGE = "生成回答时出错，请稍后重试；如持续失败请联系管理员查看后端日志。"

INSUFFICIENT_ANSWER = "知识库中未找到足够依据来回答该问题。请补充相关文档后重试。"


async def _retrieve(kbs, query, top_k, rerank):
    return await hybrid_search(kbs, query, top_k=top_k, rerank=rerank)


def _citations_from_chunks(chunks) -> list[Citation]:
    return [
        Citation(
            document_id=c.document_id,
            filename=c.filename,
            page_number=c.page_number,
            chunk_id=c.chunk_id,
            content=c.content,
            score=c.rerank_score if c.rerank_score is not None else c.score,
        )
        for c in chunks
    ]


async def answer(
    kbs: list[KnowledgeBase],
    query: str,
    top_k: int | None = None,
    rerank: bool = True,
    history: list[dict] | None = None,
) -> tuple[str, list[Citation]]:
    chunks = await _retrieve(kbs, query, top_k or settings.final_top_k, rerank)
    if not chunks:
        return INSUFFICIENT_ANSWER, []
    messages = build_messages(query, [c.__dict__ for c in chunks], history)
    result = await llm_service.chat(messages)
    text = result["choices"][0]["message"]["content"]
    return text, _citations_from_chunks(chunks)


async def answer_stream(
    kbs: list[KnowledgeBase],
    query: str,
    top_k: int | None = None,
    rerank: bool = True,
    history: list[dict] | None = None,
) -> AsyncGenerator[dict, None]:
    """流式问答。产出事件：
    {"event": "citations", "citations": [...]}  检索完成后先发送引用
    {"event": "delta", "content": "..."}         文本增量
    {"event": "done"}                            结束
    {"event": "error", "message": "..."}         出错（随后仍会发送 done）
    """
    try:
        chunks = await _retrieve(kbs, query, top_k or settings.final_top_k, rerank)
        if not chunks:
            yield {"event": "delta", "content": INSUFFICIENT_ANSWER}
            yield {"event": "done"}
            return
        yield {"event": "citations", "citations": [c.to_dict() for c in _citations_from_chunks(chunks)]}
        messages = build_messages(query, [c.__dict__ for c in chunks], history)
        async for delta in llm_service.chat_stream(messages):
            yield {"event": "delta", "content": delta}
    except Exception:  # noqa: BLE001  流已开始，无法再返回 HTTP 错误码，只能以事件告知客户端
        logger.exception("RAG 流式问答失败")
        yield {"event": "error", "message": STREAM_ERROR_MESSAGE}
    yield {"event": "done"}
