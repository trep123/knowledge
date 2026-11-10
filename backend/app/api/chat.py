import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth.permissions import require_scope
from app.database import get_db
from app.dependencies import get_authorized_knowledge_bases, get_principal
from app.schemas import ChatRequest
from app.services import rag_service

router = APIRouter(tags=["chat"])


@router.post("/chat/completions")
async def chat_completions(req: ChatRequest, principal=Depends(get_principal), db: Session = Depends(get_db)):
    """Web/REST 端 RAG 问答（与 OpenAI 兼容接口 /v1/chat/completions 区分）。"""
    require_scope(principal, "kb:chat")
    kbs = get_authorized_knowledge_bases(principal, req.knowledge_base_ids, db)

    if req.stream:
        async def event_stream():
            async for evt in rag_service.answer_stream(
                kbs, req.query, top_k=req.top_k, rerank=req.rerank, history=req.history
            ):
                yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    answer_text, citations = await rag_service.answer(
        kbs, req.query, top_k=req.top_k, rerank=req.rerank, history=req.history
    )
    return {
        "success": True,
        "answer": answer_text,
        "citations": [c.to_dict() for c in citations] if req.return_citations else [],
    }
