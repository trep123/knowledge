import httpx

from app.config import settings


async def rerank(query: str, passages: list[str]) -> list[float]:
    """调用本地 Reranker 服务（bge-reranker-v2-m3）。"""
    if not passages:
        return []
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(
            f"{settings.reranker_url}/rerank", json={"query": query, "passages": passages}
        )
        resp.raise_for_status()
        return resp.json()["scores"]
