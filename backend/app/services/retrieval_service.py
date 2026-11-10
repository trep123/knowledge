"""混合检索服务：Dense + Sparse -> RRF -> Reranker -> Top-K。

REST、OpenAI 兼容 API 共用本服务，保证结果一致。
"""
import uuid
from dataclasses import dataclass

from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchAny,
    Prefetch,
    SparseVector,
)

from app.config import settings
from app.models import KnowledgeBase
from app.rag.rrf import rrf_fuse
from app.rag.sparse import encode_sparse
from app.services import reranker_service
from app.services.embedding_service import embed_texts
from app.vector import collection_manager


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str
    knowledge_base_id: str
    filename: str
    content: str
    page_number: int | None
    chunk_index: int
    file_type: str
    score: float
    rerank_score: float | None = None


def _payload_filter(file_types: list[str] | None, document_ids: list[str] | None) -> Filter | None:
    conditions = []
    if file_types:
        conditions.append(FieldCondition(key="file_type", match=MatchAny(any=file_types)))
    if document_ids:
        conditions.append(FieldCondition(key="document_id", match=MatchAny(any=document_ids)))
    return Filter(must=conditions) if conditions else None


async def hybrid_search(
    kbs: list[KnowledgeBase],
    query: str,
    top_k: int | None = None,
    rerank: bool = True,
    filters: dict | None = None,
) -> list[RetrievedChunk]:
    top_k = top_k or settings.final_top_k
    filters = filters or {}
    qdrant = collection_manager.get_qdrant()

    dense_query = (await embed_texts([query]))[0]
    sparse_indices, sparse_values = encode_sparse(query)
    sparse_query = SparseVector(indices=sparse_indices, values=sparse_values)
    payload_filter = _payload_filter(filters.get("file_type"), filters.get("document_ids"))

    # 每个知识库独立检索（Collection 级隔离），再用应用层 RRF 跨库融合
    fused_rankings: list[list[str]] = []
    chunk_pool: dict[str, dict] = {}
    point_to_chunk: dict[str, str] = {}

    for kb in kbs:
        collection = collection_manager.collection_name(kb.id)
        if not qdrant.collection_exists(collection):
            continue
        count = qdrant.count(collection_name=collection, exact=True).count
        if count == 0:
            continue

        result = qdrant.query_points(
            collection_name=collection,
            prefetch=[
                Prefetch(
                    query=dense_query,
                    using="dense",
                    limit=settings.dense_top_k,
                    filter=payload_filter,
                ),
                Prefetch(
                    query=sparse_query,
                    using="sparse",
                    limit=settings.sparse_top_k,
                    filter=payload_filter,
                ),
            ],
            query=dense_query,  # 占位，实际融合由应用层 RRF 完成
            using="dense",
            limit=settings.rrf_top_k,
            with_payload=True,
        )

        dense_ranking: list[str] = []
        sparse_ranking: list[str] = []
        for point in result.points:
            cid = point.payload["chunk_id"]
            chunk_pool[cid] = point.payload
            point_to_chunk[str(point.id)] = cid
            dense_ranking.append(cid)
        # Sparse 单独查询以获得独立排名（RRF 需要两路各自的 rank）
        sparse_result = qdrant.query_points(
            collection_name=collection,
            query=sparse_query,
            using="sparse",
            limit=settings.sparse_top_k,
            query_filter=payload_filter,
            with_payload=False,
        )
        for point in sparse_result.points:
            cid = point_to_chunk.get(str(point.id))
            if cid is None:
                # dense 未召回该点时补充 payload
                fetched = qdrant.retrieve(collection_name=collection, ids=[point.id], with_payload=True)
                if fetched:
                    cid = fetched[0].payload["chunk_id"]
                    chunk_pool[cid] = fetched[0].payload
            if cid:
                sparse_ranking.append(cid)

        fused_rankings.append(dense_ranking)
        fused_rankings.append(sparse_ranking)

    if not chunk_pool:
        return []

    fused = rrf_fuse(fused_rankings, k=60, top_k=settings.rrf_top_k)
    candidates = [cid for cid, _ in fused if cid in chunk_pool]

    # Reranker 重排
    if rerank and candidates:
        passages = [chunk_pool[cid]["content"] for cid in candidates[: settings.reranker_top_k * 4]]
        candidates = candidates[: len(passages)]
        scores = await reranker_service.rerank(query, passages)
        scored = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
        final = scored[:top_k]
        return [
            RetrievedChunk(
                chunk_id=cid,
                document_id=chunk_pool[cid]["document_id"],
                knowledge_base_id=chunk_pool[cid]["knowledge_base_id"],
                filename=chunk_pool[cid]["filename"],
                content=chunk_pool[cid]["content"],
                page_number=chunk_pool[cid].get("page_number"),
                chunk_index=chunk_pool[cid].get("chunk_index", 0),
                file_type=chunk_pool[cid].get("file_type", ""),
                score=float(score),
                rerank_score=float(score),
            )
            for cid, score in final
        ]

    return [
        RetrievedChunk(
            chunk_id=cid,
            document_id=chunk_pool[cid]["document_id"],
            knowledge_base_id=chunk_pool[cid]["knowledge_base_id"],
            filename=chunk_pool[cid]["filename"],
            content=chunk_pool[cid]["content"],
            page_number=chunk_pool[cid].get("page_number"),
            chunk_index=chunk_pool[cid].get("chunk_index", 0),
            file_type=chunk_pool[cid].get("file_type", ""),
            score=dict(fused).get(cid, 0.0),
        )
        for cid in candidates[:top_k]
    ]


async def dense_search(kbs: list[KnowledgeBase], query: str, top_k: int = 10, filters: dict | None = None) -> list[RetrievedChunk]:
    """纯 Dense 检索（POST /search 默认行为之一）。"""
    results = await hybrid_search(kbs, query, top_k=top_k, rerank=False, filters=filters)
    return results
