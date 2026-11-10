import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_principal
from app.models import Document, Task
from app.schemas import TaskOut
from app.workers.document_tasks import process_document

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("")
def list_tasks(principal=Depends(get_principal), db: Session = Depends(get_db), limit: int = 50, status: str | None = None):
    query = db.query(Task).order_by(Task.created_at.desc()).limit(min(limit, 200))
    if status:
        query = query.filter(Task.status == status)
    return [TaskOut.model_validate(t).model_dump() for t in query.all()]


@router.get("/{task_id}")
def get_task(task_id: uuid.UUID, principal=Depends(get_principal), db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    return TaskOut.model_validate(task).model_dump()


@router.post("/{task_id}/retry")
def retry_task(task_id: uuid.UUID, principal=Depends(get_principal), db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
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
