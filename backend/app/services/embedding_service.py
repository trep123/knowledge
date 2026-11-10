import httpx

from app.config import settings


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """调用本地 Embedding 服务（bge-m3, dense 1024 维，已归一化）。"""
    if not texts:
        return []
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(f"{settings.embedding_url}/embed", json={"texts": texts})
        resp.raise_for_status()
        return resp.json()["embeddings"]


def embed_texts_sync(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    with httpx.Client(timeout=300) as client:
        resp = client.post(f"{settings.embedding_url}/embed", json={"texts": texts})
        resp.raise_for_status()
        return resp.json()["embeddings"]
