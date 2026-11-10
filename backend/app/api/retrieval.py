from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.permissions import require_scope
from app.database import get_db
from app.dependencies import get_authorized_knowledge_bases, get_principal
from app.schemas import SearchRequest, SearchResponse, SearchResultItem
from app.services.retrieval_service import hybrid_search

router = APIRouter(tags=["retrieval"])


@router.post("/search", response_model=SearchResponse)
@router.post("/search/hybrid", response_model=SearchResponse)
async def search(req: SearchRequest, principal=Depends(get_principal), db: Session = Depends(get_db)):
    require_scope(principal, "kb:search")
    kbs = get_authorized_knowledge_bases(principal, req.knowledge_base_ids, db)
    chunks = await hybrid_search(
        kbs, req.query, top_k=req.top_k, rerank=req.rerank, filters=req.filters or {}
    )
    results = [
        SearchResultItem(
            chunk_id=c.chunk_id,
            document_id=c.document_id,
            filename=c.filename,
            page_number=c.page_number,
            content=c.content,
            score=round(c.rerank_score if c.rerank_score is not None else c.score, 6),
        )
        for c in chunks
    ]
    return SearchResponse(query=req.query, results=results, total=len(results))
