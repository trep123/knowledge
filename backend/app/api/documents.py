import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.auth.permissions import require_scope
from app.database import get_db
from app.dependencies import (
    authorized_kb_id_set,
    get_authorized_knowledge_bases,
    get_principal,
)
from app.models import Document, DocumentChunk
from app.schemas import BatchIdsRequest, ChunkOut, DocumentOut, TaskOut
from app.services import document_service

router = APIRouter(tags=["documents"])


@router.post("/knowledge-bases/{kb_id}/documents", status_code=201)
async def upload_document(
    kb_id: uuid.UUID,
    principal=Depends(get_principal),
    db: Session = Depends(get_db),
    file: UploadFile = File(...),
):
    require_scope(principal, "kb:documents:upload")
    kb = get_authorized_knowledge_bases(principal, [kb_id], db)[0]
    document, action = document_service.save_and_enqueue(db, kb, file)
    return {
        "success": True,
        "action": action,  # created | duplicate
        "document": DocumentOut.model_validate(document).model_dump(),
    }


@router.post("/knowledge-bases/{kb_id}/documents/batch", status_code=201)
async def upload_documents_batch(
    kb_id: uuid.UUID,
    principal=Depends(get_principal),
    db: Session = Depends(get_db),
    files: list[UploadFile] = File(...),
):
    """批量上传：逐个校验/去重/入队，单个失败不影响其余，返回逐项结果。"""
    require_scope(principal, "kb:documents:upload")
    kb = get_authorized_knowledge_bases(principal, [kb_id], db)[0]
    results = []
    for upload in files:
        name = upload.filename
        try:
            document, action = document_service.save_and_enqueue(db, kb, upload)
            results.append(
                {"filename": name, "ok": True, "action": action, "document_id": str(document.id)}
            )
        except HTTPException as exc:
            results.append({"filename": name, "ok": False, "error": str(exc.detail)})
        except Exception as exc:
            db.rollback()
            results.append({"filename": name, "ok": False, "error": str(exc)})
    succeeded = sum(1 for r in results if r["ok"])
    return {
        "success": True,
        "total": len(results),
        "succeeded": succeeded,
        "failed": len(results) - succeeded,
        "results": results,
    }


@router.get("/knowledge-bases/{kb_id}/documents")
def list_documents(
    kb_id: uuid.UUID,
    principal=Depends(get_principal),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 50,
):
    require_scope(principal, "kb:documents:read")
    kb = get_authorized_knowledge_bases(principal, [kb_id], db)[0]
    docs = (
        db.query(Document)
        .filter(Document.knowledge_base_id == kb.id)
        .order_by(Document.created_at.desc())
        .offset(skip)
        .limit(min(limit, 200))
        .all()
    )
    return [DocumentOut.model_validate(d).model_dump() for d in docs]


def _get_authorized_document(doc_id: uuid.UUID, principal, db: Session) -> Document:
    document = db.get(Document, doc_id)
    if not document:
        raise HTTPException(404, "文档不存在")
    get_authorized_knowledge_bases(principal, [document.knowledge_base_id], db)
    return document


@router.get("/documents/{doc_id}")
def get_document(doc_id: uuid.UUID, principal=Depends(get_principal), db: Session = Depends(get_db)):
    require_scope(principal, "kb:documents:read")
    document = _get_authorized_document(doc_id, principal, db)
    return DocumentOut.model_validate(document).model_dump()


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: uuid.UUID, principal=Depends(get_principal), db: Session = Depends(get_db)):
    require_scope(principal, "kb:documents:delete")
    document = _get_authorized_document(doc_id, principal, db)
    document_service.delete_document(db, document)
    return {"success": True}


@router.post("/documents/{doc_id}/reprocess")
def reprocess_document(doc_id: uuid.UUID, principal=Depends(get_principal), db: Session = Depends(get_db)):
    require_scope(principal, "kb:documents:upload")
    document = _get_authorized_document(doc_id, principal, db)
    task = document_service.reprocess_document(db, document)
    return {"success": True, "task": TaskOut.model_validate(task).model_dump()}


@router.post("/documents/batch-delete")
def batch_delete_documents(
    req: BatchIdsRequest, principal=Depends(get_principal), db: Session = Depends(get_db)
):
    require_scope(principal, "kb:documents:delete")
    allowed = authorized_kb_id_set(principal, db)
    docs = db.query(Document).filter(Document.id.in_(req.ids)).all()
    found = {d.id for d in docs}
    results = []
    for d in docs:
        if d.knowledge_base_id not in allowed:
            results.append({"id": str(d.id), "filename": d.filename, "ok": False, "error": "无权访问"})
            continue
        try:
            document_service.delete_document(db, d)
            results.append({"id": str(d.id), "filename": d.filename, "ok": True})
        except Exception as exc:
            db.rollback()
            results.append({"id": str(d.id), "filename": d.filename, "ok": False, "error": str(exc)})
    for missing in req.ids:
        if missing not in found:
            results.append({"id": str(missing), "ok": False, "error": "文档不存在"})
    succeeded = sum(1 for r in results if r["ok"])
    return {
        "success": True,
        "total": len(results),
        "succeeded": succeeded,
        "failed": len(results) - succeeded,
        "results": results,
    }


@router.post("/documents/batch-reprocess")
def batch_reprocess_documents(
    req: BatchIdsRequest, principal=Depends(get_principal), db: Session = Depends(get_db)
):
    require_scope(principal, "kb:documents:upload")
    allowed = authorized_kb_id_set(principal, db)
    docs = db.query(Document).filter(Document.id.in_(req.ids)).all()
    found = {d.id for d in docs}
    results = []
    for d in docs:
        if d.knowledge_base_id not in allowed:
            results.append({"id": str(d.id), "filename": d.filename, "ok": False, "error": "无权访问"})
            continue
        try:
            task = document_service.reprocess_document(db, d)
            results.append({"id": str(d.id), "filename": d.filename, "ok": True, "task_id": str(task.id)})
        except Exception as exc:
            db.rollback()
            results.append({"id": str(d.id), "filename": d.filename, "ok": False, "error": str(exc)})
    for missing in req.ids:
        if missing not in found:
            results.append({"id": str(missing), "ok": False, "error": "文档不存在"})
    succeeded = sum(1 for r in results if r["ok"])
    return {
        "success": True,
        "total": len(results),
        "succeeded": succeeded,
        "failed": len(results) - succeeded,
        "results": results,
    }


@router.get("/documents/{doc_id}/chunks")
def get_document_chunks(
    doc_id: uuid.UUID,
    principal=Depends(get_principal),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 50,
):
    require_scope(principal, "kb:documents:read")
    document = _get_authorized_document(doc_id, principal, db)
    chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document.id)
        .order_by(DocumentChunk.chunk_index)
        .offset(skip)
        .limit(min(limit, 500))
        .all()
    )
    return [ChunkOut.model_validate(c).model_dump() for c in chunks]
