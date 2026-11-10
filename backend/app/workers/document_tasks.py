"""文档处理任务：解析 -> OCR -> 清洗 -> 切片 -> Embedding -> Qdrant -> PostgreSQL。"""
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.database import SessionLocal
from app.models import Document, DocumentChunk, KnowledgeBase, Task
from app.parsers import parse_document
from app.rag.chunker import chunk_text, clean_text
from app.rag.sparse import encode_sparse
from app.services.embedding_service import embed_texts_sync
from app.vector import collection_manager
from app.workers.celery_app import celery_app


def _update_progress(task_id: uuid.UUID, progress: int, status: str = "processing") -> None:
    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        if task:
            task.progress = progress
            task.status = status
            db.commit()
    finally:
        db.close()


@celery_app.task(name="process_document", bind=True, max_retries=1)
def process_document(self, document_id: str, task_id: str) -> dict:
    doc_uuid = uuid.UUID(document_id)
    task_uuid = uuid.UUID(task_id)
    db = SessionLocal()
    try:
        document = db.get(Document, doc_uuid)
        if not document:
            return {"status": "error", "message": "document not found"}
        kb = db.get(KnowledgeBase, document.knowledge_base_id)

        document.status = "processing"
        db.commit()
        _update_progress(task_uuid, 10)

        # 1. 解析（含 OCR）
        pages, page_count = parse_document(document.file_path, document.file_type)
        document.page_count = page_count
        db.commit()
        _update_progress(task_uuid, 30)

        # 2. 清洗 + 切片（按页保留页码）
        chunks: list[tuple[int | None, str]] = []
        for page_number, page_text in pages:
            text = clean_text(page_text)
            if not text:
                continue
            for piece in chunk_text(text, kb.chunk_size, kb.chunk_overlap):
                chunks.append((page_number, piece))
        if not chunks:
            raise ValueError("未能从文档中提取到任何文本")

        extracted_path = Path(settings.data_dir) / "extracted" / f"{document.id}.txt"
        extracted_path.parent.mkdir(parents=True, exist_ok=True)
        extracted_path.write_text(
            "\n\n".join(f"[第{p}页]\n{t}" for p, t in chunks), encoding="utf-8"
        )
        _update_progress(task_uuid, 45)

        # 3. 确保向量集合存在（KB 创建时的集合可能缺失），再清理旧数据（重新处理场景）
        collection_manager.create_collection(kb.id, kb.embedding_dimension)
        collection_manager.delete_document_points(kb.id, document.id)
        db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete()
        db.commit()

        # 4. Embedding（批量）
        contents = [c for _, c in chunks]
        vectors: list[list[float]] = []
        batch = 32
        for i in range(0, len(contents), batch):
            vectors.extend(embed_texts_sync(contents[i : i + batch]))
            _update_progress(task_uuid, 45 + min(35, int(35 * (i + batch) / len(contents))))

        # 5. 写入 Qdrant（dense + sparse）与 PostgreSQL
        from qdrant_client.models import PointStruct, SparseVector

        points = []
        chunk_rows = []
        for index, ((page_number, content), vector) in enumerate(zip(chunks, vectors)):
            chunk_id = uuid.uuid4()
            indices, values = encode_sparse(content)
            payload = {
                "chunk_id": str(chunk_id),
                "document_id": str(document.id),
                "knowledge_base_id": str(kb.id),
                "filename": document.filename,
                "content": content,
                "page_number": page_number,
                "chunk_index": index,
                "file_type": document.file_type,
                "document_version": document.version,
            }
            points.append(
                PointStruct(
                    id=str(chunk_id),
                    vector={"dense": vector, "sparse": SparseVector(indices=indices, values=values)},
                    payload=payload,
                )
            )
            chunk_rows.append(
                DocumentChunk(
                    id=chunk_id,
                    document_id=document.id,
                    knowledge_base_id=kb.id,
                    chunk_index=index,
                    content=content,
                    page_number=page_number,
                    metadata_={"char_len": len(content)},
                    qdrant_point_id=chunk_id,
                )
            )

        client = collection_manager.get_qdrant()
        collection = collection_manager.collection_name(kb.id)
        upsert_batch = 256
        for i in range(0, len(points), upsert_batch):
            client.upsert(collection_name=collection, points=points[i : i + upsert_batch])
        db.add_all(chunk_rows)

        document.status = "ready"
        document.chunk_count = len(chunk_rows)
        document.error_message = None
        task = db.get(Task, task_uuid)
        task.status = "completed"
        task.progress = 100
        task.finished_at = datetime.now(timezone.utc)
        db.commit()
        return {"status": "completed", "chunks": len(chunk_rows)}
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        message = str(exc)[:2000]
        document = db.get(Document, doc_uuid)
        if document:
            document.status = "failed"
            document.error_message = message
        task = db.get(Task, task_uuid)
        if task:
            task.status = "failed"
            task.error_message = message
            task.finished_at = datetime.now(timezone.utc)
        db.commit()
        return {"status": "failed", "message": message}
    finally:
        db.close()
