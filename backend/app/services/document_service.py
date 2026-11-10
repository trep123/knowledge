"""文档服务：上传校验、SHA256 去重、存储、创建处理任务。"""
import hashlib
import re
import shutil
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Document, KnowledgeBase, Task
from app.workers.document_tasks import process_document


def _safe_filename(filename: str) -> str:
    """防路径穿越：仅保留基础文件名并过滤危险字符。"""
    name = Path(filename or "unnamed").name
    name = re.sub(r"[^\w\u4e00-\u9fff.\-]", "_", name)
    return name[:200] or "unnamed"


def save_and_enqueue(
    db: Session, kb: KnowledgeBase, upload: UploadFile
) -> tuple[Document, str]:
    filename = _safe_filename(upload.filename)
    ext = Path(filename).suffix.lower()
    if ext not in settings.allowed_extensions:
        raise HTTPException(400, f"不支持的文件类型: {ext}")

    # 读取并做大小/哈希检查
    hasher = hashlib.sha256()
    tmp_dir = Path(settings.data_dir) / "temporary"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"upload_{uuid.uuid4().hex}"

    size = 0
    max_bytes = settings.max_upload_mb * 1024 * 1024
    with open(tmp_path, "wb") as f:
        while chunk := upload.file.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                f.close()
                tmp_path.unlink(missing_ok=True)
                raise HTTPException(413, f"文件超过大小限制 {settings.max_upload_mb}MB")
            hasher.update(chunk)
            f.write(chunk)

    # 头部魔数校验
    with open(tmp_path, "rb") as f:
        header = f.read(8)
    magic_ok = {
        ".pdf": header.startswith(b"%PDF"),
        ".docx": header.startswith(b"PK\x03\x04"),
        ".png": header.startswith(b"\x89PNG"),
        ".jpg": header.startswith(b"\xff\xd8"),
        ".jpeg": header.startswith(b"\xff\xd8"),
        ".tif": header[:4] in (b"II\x2a\x00", b"MM\x00\x2a"),
        ".tiff": header[:4] in (b"II\x2a\x00", b"MM\x00\x2a"),
    }
    if ext in magic_ok and not magic_ok[ext]:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(400, "文件内容与扩展名不符（魔数校验失败）")

    file_hash = hasher.hexdigest()

    # SHA256 去重（同一知识库内）
    existing = (
        db.query(Document)
        .filter(
            Document.knowledge_base_id == kb.id,
            Document.file_hash == file_hash,
            Document.status != "failed",
        )
        .first()
    )
    if existing:
        tmp_path.unlink(missing_ok=True)
        return existing, "duplicate"

    document = Document(
        id=uuid.uuid4(),
        knowledge_base_id=kb.id,
        filename=filename,
        file_type=ext.lstrip("."),
        file_hash=file_hash,
        file_size=size,
        status="pending",
    )
    dest_dir = Path(settings.data_dir) / "documents" / kb.vector_collection / str(document.id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / filename
    shutil.move(str(tmp_path), str(dest_path))
    document.file_path = str(dest_path)

    task = Task(task_type="process_document", document_id=document.id, status="pending")
    db.add(document)
    db.add(task)
    db.commit()
    db.refresh(document)
    db.refresh(task)

    process_document.delay(str(document.id), str(task.id))
    return document, "created"


def delete_document(db: Session, document: Document) -> None:
    from app.vector import collection_manager

    kb = db.get(KnowledgeBase, document.knowledge_base_id)
    if kb:
        collection_manager.delete_document_points(kb.id, document.id)
    file_path = Path(document.file_path)
    if file_path.exists():
        file_path.unlink()
    extracted = Path(settings.data_dir) / "extracted" / f"{document.id}.txt"
    extracted.unlink(missing_ok=True)
    db.delete(document)
    db.commit()


def reprocess_document(db: Session, document: Document) -> Task:
    document.status = "pending"
    document.version += 1
    document.error_message = None
    task = Task(task_type="process_document", document_id=document.id, status="pending")
    db.add(task)
    db.commit()
    db.refresh(task)
    process_document.delay(str(document.id), str(task.id))
    return task
