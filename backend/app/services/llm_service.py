import json
from collections.abc import AsyncGenerator

import httpx

from app.config import settings


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.llm_api_key}"}


async def chat(messages: list[dict], temperature: float = 0.3, max_tokens: int = 2048) -> dict:
    async with httpx.AsyncClient(timeout=600) as client:
        resp = await client.post(
            f"{settings.llm_base_url}/chat/completions",
            headers=_headers(),
            json={
                "model": settings.llm_model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def chat_stream(
    messages: list[dict], temperature: float = 0.3, max_tokens: int = 2048
) -> AsyncGenerator[str, None]:
    """流式调用本地 LLM，逐段产出文本增量。"""
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream(
            "POST",
            f"{settings.llm_base_url}/chat/completions",
            headers=_headers(),
            json={
                "model": settings.llm_model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
            },
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                choices = chunk.get("choices") or []
                if choices:
                    delta = choices[0].get("delta", {}).get("content")
                    if delta:
                        yield delta
