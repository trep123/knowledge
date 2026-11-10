import os
from contextlib import asynccontextmanager

import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

MODEL_TYPE = os.environ.get("MODEL_TYPE", "embedding")
MODEL_PATH = os.environ.get("MODEL_PATH", "/models/bge-m3")
PORT = int(os.environ.get("PORT", "8001"))

state: dict = {}


def load_model():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if MODEL_TYPE == "embedding":
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(MODEL_PATH, device=device, trust_remote_code=False)
        model.max_seq_length = 4096
        state["model"] = model
        state["dim"] = model.get_sentence_embedding_dimension()
    elif MODEL_TYPE == "reranker":
        from sentence_transformers import CrossEncoder

        state["model"] = CrossEncoder(MODEL_PATH, device=device, max_length=1024)
    else:
        raise RuntimeError(f"unknown MODEL_TYPE: {MODEL_TYPE}")
    state["device"] = device


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_model()
    yield


app = FastAPI(title=f"kb-model-server ({MODEL_TYPE})", lifespan=lifespan)


class EmbedRequest(BaseModel):
    texts: list[str]


class RerankRequest(BaseModel):
    query: str
    passages: list[str]


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model_type": MODEL_TYPE,
        "model_path": MODEL_PATH,
        "device": state.get("device"),
        "dim": state.get("dim"),
    }


@app.post("/embed")
def embed(req: EmbedRequest):
    if MODEL_TYPE != "embedding":
        raise HTTPException(400, "this instance is not an embedding server")
    if not req.texts:
        return {"embeddings": [], "dim": state["dim"]}
    vectors = state["model"].encode(
        req.texts, normalize_embeddings=True, batch_size=16, show_progress_bar=False
    )
    return {"embeddings": vectors.tolist(), "dim": state["dim"]}


@app.post("/rerank")
def rerank(req: RerankRequest):
    if MODEL_TYPE != "reranker":
        raise HTTPException(400, "this instance is not a reranker server")
    if not req.passages:
        return {"scores": []}
    pairs = [[req.query, p] for p in req.passages]
    scores = state["model"].predict(pairs, show_progress_bar=False)
    return {"scores": [float(s) for s in scores]}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
