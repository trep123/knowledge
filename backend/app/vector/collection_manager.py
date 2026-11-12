"""Qdrant Collection 管理：每个知识库独立 Collection（dense + sparse）。"""
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    HnswConfigDiff,
    Modifier,
    PayloadSchemaType,
    SparseVectorParams,
    VectorParams,
)

from app.config import settings

_client: QdrantClient | None = None

PAYLOAD_INDEX_FIELDS = ["document_id", "knowledge_base_id", "file_type", "page_number", "document_version"]


def get_qdrant() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=settings.qdrant_url, timeout=60)
    return _client


def collection_name(kb_id: uuid.UUID) -> str:
    return f"kb_{kb_id.hex[:16]}"


def create_collection(kb_id: uuid.UUID, dimension: int) -> str:
    name = collection_name(kb_id)
    client = get_qdrant()
    if client.collection_exists(name):
        return name
    client.create_collection(
        collection_name=name,
        vectors_config={"dense": VectorParams(size=dimension, distance=Distance.COSINE, hnsw_config=HnswConfigDiff(m=16, ef_construct=200))},
        sparse_vectors_config={
            "sparse": SparseVectorParams(modifier=Modifier.IDF)
        },
    )
    for field in PAYLOAD_INDEX_FIELDS:
        schema = PayloadSchemaType.INTEGER if field in ("page_number", "document_version") else PayloadSchemaType.KEYWORD
        client.create_payload_index(collection_name=name, field_name=field, field_schema=schema)
    return name


def delete_collection(kb_id: uuid.UUID) -> None:
    name = collection_name(kb_id)
    client = get_qdrant()
    if client.collection_exists(name):
        client.delete_collection(name)


def delete_document_points(
    kb_id: uuid.UUID, document_id: uuid.UUID, keep_version: int | None = None
) -> None:
    """删除文档的向量点；指定 keep_version 时只删除其他版本（重处理时清理旧版本）。"""
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    client = get_qdrant()
    name = collection_name(kb_id)
    if not client.collection_exists(name):
        return
    must = [FieldCondition(key="document_id", match=MatchValue(value=str(document_id)))]
    must_not = (
        [FieldCondition(key="document_version", match=MatchValue(value=keep_version))]
        if keep_version is not None
        else None
    )
    client.delete(collection_name=name, points_selector=Filter(must=must, must_not=must_not))


def delete_document_version_points(kb_id: uuid.UUID, document_id: uuid.UUID, version: int) -> None:
    """删除文档某一版本的向量点（清理同版本失败重试留下的残留）。"""
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    client = get_qdrant()
    name = collection_name(kb_id)
    if not client.collection_exists(name):
        return
    client.delete(
        collection_name=name,
        points_selector=Filter(
            must=[
                FieldCondition(key="document_id", match=MatchValue(value=str(document_id))),
                FieldCondition(key="document_version", match=MatchValue(value=version)),
            ]
        ),
    )
