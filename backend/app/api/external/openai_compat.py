"""OpenAI Compatible API：GET /v1/models、POST /v1/chat/completions（含 SSE 流式）。

扩展参数：knowledge_base_ids / top_k / rerank。
不能传扩展参数的客户端可在 API Key 上绑定默认知识库（default_kb_ids）。
"""
import json
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.permissions import require_scope
from app.database import get_db
from app.dependencies import get_authorized_knowledge_bases, get_principal
from app.services import rag_service
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/v1", tags=["openai-compat"])

MODEL_NAME = "knowledge-base"


class OpenAIChatMessage(BaseModel):
    role: str
    content: str


class OpenAIChatRequest(BaseModel):
    model: str = MODEL_NAME
    messages: list[OpenAIChatMessage] = Field(min_length=1)
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None
    # 本平台扩展参数
    knowledge_base_ids: list[uuid.UUID] | None = None
    top_k: int = Field(default=5, ge=1, le=50)
    rerank: bool = True
    return_citations: bool = False


def _resolve_query_and_history(messages: list[OpenAIChatMessage]) -> tuple[str, list[dict]]:
    """取最后一条 user 消息作为检索问题，之前的对话作为 history。"""
    last_user_index = None
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].role == "user":
            last_user_index = i
            break
    if last_user_index is None:
        raise HTTPException(400, "messages 中必须包含 user 消息")
    query = messages[last_user_index].content
    history = [m.model_dump() for m in messages[:last_user_index]]
    return query, history


def _resolve_kb_ids(req: OpenAIChatRequest, principal) -> list[uuid.UUID] | None:
    if req.knowledge_base_ids:
        return req.knowledge_base_ids
    if principal.kind == "api_key" and principal.api_key.default_kb_ids:
        return [uuid.UUID(k) for k in principal.api_key.default_kb_ids]
    return None  # 未指定时使用主体授权的全部知识库


@router.get("/models")
def list_models(principal=Depends(get_principal)):
    require_scope(principal, "kb:chat")
    return {
        "object": "list",
        "data": [
            {
                "id": MODEL_NAME,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "local-knowledge-base",
            }
        ],
    }


@router.post("/chat/completions")
async def chat_completions(req: OpenAIChatRequest, request: Request, principal=Depends(get_principal), db: Session = Depends(get_db)):
    require_scope(principal, "kb:chat")
    kbs = get_authorized_knowledge_bases(principal, _resolve_kb_ids(req, principal), db)
    query, history = _resolve_query_and_history(req.messages)
    completion_id = f"chatcmpl-kb-{uuid.uuid4().hex[:12]}"
    created = int(time.time())

    if req.stream:
        async def event_stream():
            async for evt in rag_service.answer_stream(kbs, query, top_k=req.top_k, rerank=req.rerank, history=history):
                if evt["event"] == "citations":
                    if req.return_citations:
                        chunk = {
                            "id": completion_id,
                            "object": "chat.completion.chunk",
                            "created": created,
                            "model": MODEL_NAME,
                            "kb_citations": evt["citations"],
                            "choices": [],
                        }
                        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                elif evt["event"] == "delta":
                    chunk = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": MODEL_NAME,
                        "choices": [{"index": 0, "delta": {"content": evt["content"]}, "finish_reason": None}],
                    }
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                elif evt["event"] == "error":
                    err = {"error": {"message": evt["message"], "type": "server_error", "code": "rag_failed"}}
                    yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"
                elif evt["event"] == "done":
                    chunk = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": MODEL_NAME,
                        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                    }
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    answer_text, citations = await rag_service.answer(kbs, query, top_k=req.top_k, rerank=req.rerank, history=history)
    response = {
        "id": completion_id,
        "object": "chat.completion",
        "created": created,
        "model": MODEL_NAME,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": answer_text},
                "finish_reason": "stop",
            }
        ],
    }
    if req.return_citations:
        response["kb_citations"] = [c.to_dict() for c in citations]
    return response
