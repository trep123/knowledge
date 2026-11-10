from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "production"
    app_secret_key: str = "change-this-secret"
    jwt_secret_key: str = "change-this-secret"
    jwt_expire_hours: int = 12

    database_url: str = "postgresql+psycopg2://kbuser:pass@postgres:5432/knowledge_base"
    redis_url: str = "redis://redis:6379/0"
    qdrant_url: str = "http://qdrant:6333"

    embedding_url: str = "http://embedding:8001"
    reranker_url: str = "http://reranker:8002"
    llm_base_url: str = "http://llm:8080/v1"
    llm_api_key: str = ""
    llm_model: str = "qwen3-8b"

    api_default_rate_limit: int = 60

    admin_username: str = "admin"
    admin_password: str = ""

    data_dir: Path = Path("/app/data")

    # 切片单位为“字符数”（全系统统一，不混用 token 计量）
    chunk_size: int = 800
    chunk_overlap: int = 120

    # 检索参数（方案 11.2）
    dense_top_k: int = 30
    sparse_top_k: int = 30
    rrf_top_k: int = 40
    reranker_top_k: int = 10
    final_top_k: int = 5

    embedding_model_name: str = "bge-m3"
    embedding_dimension: int = 1024

    max_upload_mb: int = 200
    allowed_extensions: set[str] = {
        ".pdf", ".docx", ".md", ".markdown", ".txt",
        ".png", ".jpg", ".jpeg", ".tiff", ".tif",
    }

    model_config = {"extra": "ignore"}


settings = Settings()
