import uuid
from datetime import datetime

import re

from pydantic import BaseModel, Field, field_validator


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


class UserOut(BaseModel):
    id: uuid.UUID
    username: str
    email: str | None
    role: str
    status: str
    last_login_at: datetime | None = None
    locked_until: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


USERNAME_PATTERN = r"^[A-Za-z0-9_.\-]{3,50}$"
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _check_password(value: str) -> str:
    if len(value) < 8 or len(value) > 128:
        raise ValueError("密码长度需为 8-128 位")
    if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
        raise ValueError("密码需同时包含字母和数字")
    return value


def _check_email(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    if len(value) > 255 or not EMAIL_PATTERN.match(value):
        raise ValueError("邮箱格式不正确")
    return value


class UserCreate(BaseModel):
    username: str = Field(pattern=USERNAME_PATTERN, description="3-50 位字母、数字、_ . -")
    password: str
    email: str | None = None
    role: str = "user"

    @field_validator("password")
    @classmethod
    def _validate_password(cls, v: str) -> str:
        return _check_password(v)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, v: str | None) -> str | None:
        return _check_email(v)


class UserUpdate(BaseModel):
    email: str | None = None
    role: str | None = None
    status: str | None = None

    @field_validator("email")
    @classmethod
    def _validate_email(cls, v: str | None) -> str | None:
        return _check_email(v)


class PasswordReset(BaseModel):
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _validate_new_password(cls, v: str) -> str:
        return _check_password(v)


class PasswordChange(BaseModel):
    old_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _validate_new_password(cls, v: str) -> str:
        return _check_password(v)


class UserListOut(BaseModel):
    total: int
    items: list[UserOut]


class KnowledgeBaseMembersUpdate(BaseModel):
    user_ids: list[uuid.UUID] = Field(default_factory=list, max_length=1000)


class MemberOut(BaseModel):
    id: uuid.UUID
    username: str
    email: str | None
    role: str
    status: str

    model_config = {"from_attributes": True}


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    chunk_size: int = Field(default=800, ge=100, le=4000)
    chunk_overlap: int = Field(default=120, ge=0, le=1000)


class KnowledgeBaseUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    chunk_size: int | None = Field(default=None, ge=100, le=4000)
    chunk_overlap: int | None = Field(default=None, ge=0, le=1000)


class BatchIdsRequest(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=1000)


class KnowledgeBaseOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    owner_id: uuid.UUID
    embedding_model: str
    embedding_dimension: int
    vector_collection: str
    chunk_size: int
    chunk_overlap: int
    status: str
    created_at: datetime
    document_count: int = 0

    model_config = {"from_attributes": True}


class DocumentOut(BaseModel):
    id: uuid.UUID
    knowledge_base_id: uuid.UUID
    filename: str
    file_type: str
    file_size: int
    page_count: int | None
    chunk_count: int
    status: str
    version: int
    error_message: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChunkOut(BaseModel):
    id: uuid.UUID
    chunk_index: int
    content: str
    page_number: int | None

    model_config = {"from_attributes": True}


class TaskOut(BaseModel):
    id: uuid.UUID
    task_type: str
    document_id: uuid.UUID | None
    status: str
    progress: int
    error_message: str | None
    created_at: datetime
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class SearchRequest(BaseModel):
    knowledge_base_ids: list[uuid.UUID] | None = None
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)
    rerank: bool = True
    filters: dict | None = None


class SearchResultItem(BaseModel):
    chunk_id: str
    document_id: str
    filename: str
    page_number: int | None
    content: str
    score: float


class SearchResponse(BaseModel):
    success: bool = True
    query: str
    results: list[SearchResultItem]
    total: int


class ChatRequest(BaseModel):
    knowledge_base_ids: list[uuid.UUID] | None = None
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)
    rerank: bool = True
    return_citations: bool = True
    stream: bool = False
    history: list[dict] | None = None


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    scopes: list[str] = Field(default_factory=lambda: ["kb:read", "kb:search", "kb:chat"])
    knowledge_base_ids: list[uuid.UUID] = Field(default_factory=list)
    default_kb_ids: list[uuid.UUID] = Field(default_factory=list)
    rate_limit: int = Field(default=60, ge=1, le=10000)
    daily_limit: int = Field(default=10000, ge=1)
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)


class ApiKeyUpdate(BaseModel):
    name: str | None = None
    scopes: list[str] | None = None
    knowledge_base_ids: list[uuid.UUID] | None = None
    default_kb_ids: list[uuid.UUID] | None = None
    rate_limit: int | None = Field(default=None, ge=1, le=10000)
    daily_limit: int | None = Field(default=None, ge=1)
    status: str | None = None
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)


class ApiKeyOut(BaseModel):
    id: uuid.UUID
    name: str
    key_prefix: str
    scopes: list
    knowledge_base_ids: list[str] = []
    default_kb_ids: list = []
    rate_limit: int
    daily_limit: int
    status: str
    last_used_at: datetime | None
    expires_at: datetime | None
    created_at: datetime
