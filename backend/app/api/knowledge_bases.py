import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.permissions import require_scope
from app.config import settings
from app.database import get_db
from app.dependencies import (
    authorized_kb_id_set,
    get_authorized_knowledge_bases,
    get_principal,
)
from app.models import Document, KnowledgeBase, KnowledgeBaseMember, User
from app.schemas import (
    BatchIdsRequest,
    KnowledgeBaseCreate,
    KnowledgeBaseMembersUpdate,
    KnowledgeBaseOut,
    KnowledgeBaseUpdate,
    MemberOut,
)
from app.vector import collection_manager

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-bases"])


def _with_count(db: Session, kbs: list[KnowledgeBase]) -> list[dict]:
    counts = dict(
        db.query(Document.knowledge_base_id, func.count(Document.id))
        .filter(Document.knowledge_base_id.in_([kb.id for kb in kbs]))
        .group_by(Document.knowledge_base_id)
        .all()
    ) if kbs else {}
    out = []
    for kb in kbs:
        data = KnowledgeBaseOut.model_validate(kb).model_dump()
        data["document_count"] = counts.get(kb.id, 0)
        out.append(data)
    return out


@router.get("")
def list_knowledge_bases(
    principal=Depends(get_principal), db: Session = Depends(get_db)
):
    require_scope(principal, "kb:read")
    allowed = authorized_kb_id_set(principal, db)
    if not allowed:
        return []  # 新用户尚未被授权任何知识库时返回空列表，而不是报错
    kbs = (
        db.query(KnowledgeBase)
        .filter(KnowledgeBase.id.in_(allowed))
        .order_by(KnowledgeBase.created_at.desc())
        .all()
    )
    return _with_count(db, kbs)


@router.post("", status_code=201)
def create_knowledge_base(
    req: KnowledgeBaseCreate, principal=Depends(get_principal), db: Session = Depends(get_db)
):
    require_scope(principal, "kb:admin")
    kb = KnowledgeBase(
        name=req.name,
        description=req.description,
        owner_id=principal.user_id,
        embedding_model=settings.embedding_model_name,
        embedding_dimension=settings.embedding_dimension,
        vector_collection="",  # 先占位，拿到 id 后生成
        chunk_size=req.chunk_size,
        chunk_overlap=req.chunk_overlap,
    )
    db.add(kb)
    db.flush()
    kb.vector_collection = collection_manager.collection_name(kb.id)
    db.commit()
    db.refresh(kb)
    collection_manager.create_collection(kb.id, kb.embedding_dimension)
    return KnowledgeBaseOut.model_validate(kb).model_dump() | {"document_count": 0}


@router.get("/{kb_id}")
def get_knowledge_base(
    kb_id: uuid.UUID, principal=Depends(get_principal), db: Session = Depends(get_db)
):
    require_scope(principal, "kb:read")
    kb = get_authorized_knowledge_bases(principal, [kb_id], db)[0]
    return _with_count(db, [kb])[0]


@router.put("/{kb_id}")
def update_knowledge_base(
    kb_id: uuid.UUID,
    req: KnowledgeBaseUpdate,
    principal=Depends(get_principal),
    db: Session = Depends(get_db),
):
    require_scope(principal, "kb:admin")
    kb = get_authorized_knowledge_bases(principal, [kb_id], db)[0]
    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(kb, field, value)
    db.commit()
    db.refresh(kb)
    return _with_count(db, [kb])[0]


def _get_manageable_kb(kb_id: uuid.UUID, principal, db: Session) -> KnowledgeBase:
    """知识库授权只能由管理员或知识库所有者（Web 用户）操作。"""
    if principal.kind != "user":
        raise HTTPException(403, "知识库授权仅支持 Web 用户操作")
    kb = db.get(KnowledgeBase, kb_id)
    if not kb or kb.status != "active":
        raise HTTPException(404, "知识库不存在")
    if not principal.is_admin and kb.owner_id != principal.user_id:
        raise HTTPException(403, "仅管理员或知识库所有者可设置授权")
    return kb


@router.get("/{kb_id}/members")
def list_members(kb_id: uuid.UUID, principal=Depends(get_principal), db: Session = Depends(get_db)):
    kb = _get_manageable_kb(kb_id, principal, db)
    users = (
        db.query(User)
        .join(KnowledgeBaseMember, KnowledgeBaseMember.user_id == User.id)
        .filter(KnowledgeBaseMember.knowledge_base_id == kb.id)
        .order_by(User.username)
        .all()
    )
    return [MemberOut.model_validate(u).model_dump() for u in users]


@router.put("/{kb_id}/members")
def set_members(
    kb_id: uuid.UUID,
    req: KnowledgeBaseMembersUpdate,
    principal=Depends(get_principal),
    db: Session = Depends(get_db),
):
    """整体替换知识库的授权用户列表（所有者无需授权，自动拥有访问权）。"""
    kb = _get_manageable_kb(kb_id, principal, db)
    wanted = {uid for uid in req.user_ids if uid != kb.owner_id}
    if wanted:
        found = {row[0] for row in db.query(User.id).filter(User.id.in_(wanted)).all()}
        missing = [str(u) for u in wanted - found]
        if missing:
            raise HTTPException(400, f"用户不存在: {missing}")
    db.query(KnowledgeBaseMember).filter(KnowledgeBaseMember.knowledge_base_id == kb.id).delete()
    for uid in wanted:
        db.add(KnowledgeBaseMember(knowledge_base_id=kb.id, user_id=uid))
    db.commit()
    return list_members(kb_id, principal, db)


def _delete_kb(db: Session, kb: KnowledgeBase) -> None:
    """删除知识库：向量集合 + 全部文档（含文件）+ 记录本身。调用方负责 commit。"""
    from app.services.document_service import delete_document

    collection_manager.delete_collection(kb.id)
    for doc in list(kb.documents):
        delete_document(db, doc)
    db.query(KnowledgeBaseMember).filter(KnowledgeBaseMember.knowledge_base_id == kb.id).delete()
    kb.status = "deleted"
    db.delete(kb)


@router.delete("/{kb_id}")
def delete_knowledge_base(
    kb_id: uuid.UUID, principal=Depends(get_principal), db: Session = Depends(get_db)
):
    require_scope(principal, "kb:admin")
    kb = get_authorized_knowledge_bases(principal, [kb_id], db)[0]
    _delete_kb(db, kb)
    db.commit()
    return {"success": True}


@router.post("/batch-delete")
def batch_delete_knowledge_bases(
    req: BatchIdsRequest, principal=Depends(get_principal), db: Session = Depends(get_db)
):
    require_scope(principal, "kb:admin")
    allowed = authorized_kb_id_set(principal, db)
    kbs = db.query(KnowledgeBase).filter(KnowledgeBase.id.in_(req.ids)).all()
    found = {kb.id for kb in kbs}
    results = []
    for kb in kbs:
        if kb.id not in allowed:
            results.append({"id": str(kb.id), "name": kb.name, "ok": False, "error": "无权访问"})
            continue
        try:
            _delete_kb(db, kb)
            db.commit()
            results.append({"id": str(kb.id), "name": kb.name, "ok": True})
        except Exception as exc:  # 单个失败不影响其余
            db.rollback()
            results.append({"id": str(kb.id), "name": kb.name, "ok": False, "error": str(exc)})
    for missing in req.ids:
        if missing not in found:
            results.append({"id": str(missing), "ok": False, "error": "知识库不存在"})
    succeeded = sum(1 for r in results if r["ok"])
    return {
        "success": True,
        "total": len(results),
        "succeeded": succeeded,
        "failed": len(results) - succeeded,
        "results": results,
    }
