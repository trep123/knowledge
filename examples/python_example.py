#!/usr/bin/env python3
"""外部 API 调用示例（Python）——使用 API Key，无需登录账户。

依赖: pip install requests
运行:
    export KB_API_KEY="kb-你的APIKey"
    python3 examples/python_example.py

可选环境变量:
    KB_BASE_URL  默认 http://localhost:8080
    KB_ID        知识库 UUID；不填则用 API Key 绑定的默认知识库
    KB_QUERY     提问内容

所有请求都用 `Authorization: Bearer <API Key>` 鉴权。
"""
import json
import os

import requests

BASE_URL = os.getenv("KB_BASE_URL", "http://localhost:8080").rstrip("/")
API_KEY = os.getenv("KB_API_KEY", "")
KB_ID = os.getenv("KB_ID", "")
QUERY = os.getenv("KB_QUERY", "删除文档时需要注意什么？")

if not API_KEY:
    raise SystemExit('请先设置环境变量 KB_API_KEY，例如 export KB_API_KEY="kb-xxxx"')

HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
# KB_ID 为空则省略，走 API Key 的默认知识库/授权范围
KB_IDS = [KB_ID] if KB_ID else None


def hr(title: str) -> None:
    print(f"\n\033[1;36m== {title} ==\033[0m")


def list_models() -> None:
    hr("1) GET /v1/models —— 列出可用模型")
    r = requests.get(f"{BASE_URL}/v1/models", headers=HEADERS, timeout=30)
    r.raise_for_status()
    print(json.dumps(r.json(), ensure_ascii=False, indent=2))


def chat() -> None:
    hr("2) POST /v1/chat/completions —— 非流式问答（OpenAI 兼容）")
    payload = {
        "model": "knowledge-base",
        "messages": [{"role": "user", "content": QUERY}],
        "top_k": 5,
        "rerank": True,
        "return_citations": True,
    }
    if KB_IDS:
        payload["knowledge_base_ids"] = KB_IDS
    r = requests.post(f"{BASE_URL}/v1/chat/completions", headers=HEADERS, json=payload, timeout=120)
    r.raise_for_status()
    data = r.json()
    print("回答:", data["choices"][0]["message"]["content"])
    for c in data.get("kb_citations", []):
        print(f"  引用[{c['score']:.4f}] {c['filename']} p{c.get('page_number')}: {c['content'][:50]}…")


def chat_stream() -> None:
    hr("3) POST /v1/chat/completions —— SSE 流式问答（逐字打印）")
    payload = {
        "model": "knowledge-base",
        "stream": True,
        "messages": [{"role": "user", "content": QUERY}],
        "return_citations": True,
    }
    if KB_IDS:
        payload["knowledge_base_ids"] = KB_IDS
    print("回答: ", end="", flush=True)
    with requests.post(
        f"{BASE_URL}/v1/chat/completions", headers=HEADERS, json=payload, stream=True, timeout=300
    ) as r:
        r.raise_for_status()
        for raw in r.iter_lines(decode_unicode=True):
            if not raw or not raw.startswith("data:"):
                continue
            chunk = raw[len("data:"):].strip()
            if chunk == "[DONE]":
                break
            obj = json.loads(chunk)
            # 首个带 kb_citations 的 chunk 是引用；其余是正文增量
            if obj.get("kb_citations"):
                names = ", ".join(c["filename"] for c in obj["kb_citations"])
                print(f"\n[引用来源: {names}]\n回答: ", end="", flush=True)
                continue
            delta = obj["choices"][0]["delta"].get("content") if obj.get("choices") else None
            if delta:
                print(delta, end="", flush=True)
    print()


def search() -> None:
    hr("4) POST /api/v1/search —— 混合检索（只返回证据片段）")
    payload = {"query": QUERY, "top_k": 5, "rerank": True}
    if KB_IDS:
        payload["knowledge_base_ids"] = KB_IDS
    r = requests.post(f"{BASE_URL}/api/v1/search", headers=HEADERS, json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    print(f"命中 {data['total']} 条:")
    for item in data["results"]:
        print(f"  [{item['score']:.4f}] {item['filename']} p{item.get('page_number')}: {item['content'][:60]}…")


def chat_with_openai_sdk() -> None:
    """可选：直接用 OpenAI 官方 SDK（pip install openai）接入本平台。"""
    hr("5) 可选：OpenAI SDK 方式")
    try:
        from openai import OpenAI
    except ImportError:
        print("（未安装 openai 库，跳过。pip install openai 后可用）")
        return
    client = OpenAI(base_url=f"{BASE_URL}/v1", api_key=API_KEY)
    extra = {"top_k": 5, "return_citations": True}
    if KB_IDS:
        extra["knowledge_base_ids"] = KB_IDS
    resp = client.chat.completions.create(
        model="knowledge-base",
        messages=[{"role": "user", "content": QUERY}],
        extra_body=extra,
    )
    print("回答:", resp.choices[0].message.content)


if __name__ == "__main__":
    list_models()
    chat()
    chat_stream()
    search()
    chat_with_openai_sdk()
    hr("完成")
    print("提示: 401=Key 无效/缺失, 403=scope 不足或无权访问知识库, 429=触发限流")
