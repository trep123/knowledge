import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.permissions import require_scope
from app.database import get_db
from app.dependencies import authorized_kb_id_set, get_principal
from app.models import Document, Task
from app.schemas import TaskOut
from app.workers.document_tasks import process_document

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _authorized_task(task_id: uuid.UUID, principal, db: Session) -> Task:
    """任务通过其文档归属的知识库鉴权；文档已删除的任务仅管理员可见。"""
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    document = db.get(Document, task.document_id) if task.document_id else None
    if document is None:
        if not principal.is_admin:
            raise HTTPException(404, "任务不存在")
        return task
    if document.knowledge_base_id not in authorized_kb_id_set(principal, db):
        raise HTTPException(404, "任务不存在")
    return task


@router.get("")
def list_tasks(
    principal=Depends(get_principal),
    db: Session = Depends(get_db),
    limit: int = 50,
    status: str | None = None,
):
    require_scope(principal, "kb:documents:read")
    query = db.query(Task)
    if not principal.is_admin:
        allowed = authorized_kb_id_set(principal, db)
        if not allowed:
            return []
        query = query.join(Document, Document.id == Task.document_id).filter(
            Document.knowledge_base_id.in_(allowed)
        )
    if status:
        query = query.filter(Task.status == status)
    query = query.order_by(Task.created_at.desc()).limit(min(max(limit, 1), 200))
    return [TaskOut.model_validate(t).model_dump() for t in query.all()]


@router.get("/{task_id}")
def get_task(task_id: uuid.UUID, principal=Depends(get_principal), db: Session = Depends(get_db)):
    require_scope(principal, "kb:documents:read")
    return TaskOut.model_validate(_authorized_task(task_id, principal, db)).model_dump()


@router.post("/{task_id}/retry")
def retry_task(task_id: uuid.UUID, principal=Depends(get_principal), db: Session = Depends(get_db)):
    require_scope(principal, "kb:documents:upload")
    task = _authorized_task(task_id, principal, db)
    if task.status not in ("failed",):
        raise HTTPException(400, "仅失败任务可重试")
    document = db.get(Document, task.document_id) if task.document_id else None
    if not document:
        raise HTTPException(400, "关联文档不存在")
    document.status = "pending"
    task.status = "pending"
    task.progress = 0
    task.error_message = None
    db.commit()
    process_document.delay(str(document.id), str(task.id))
    return {"success": True, "task": TaskOut.model_validate(task).model_dump()}
