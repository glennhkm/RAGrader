"""Deterministic OpenAI-compatible stand-in for the LLM and embedding providers.

Used only by the compose integration tests so the full stack runs without any
external service or API key:

* ``POST /v1/embeddings`` returns 64-dim hashed bag-of-words vectors.
* ``POST /v1/chat/completions`` returns a JSON grade that cites every
  ``*.txt`` / ``*.pdf`` source named in the prompt (score 80, confidence 0.85).
"""

import hashlib
import json
import math
import re
from typing import Any, List, Union

from fastapi import FastAPI, Request

DIMENSION = 64
SOURCE_PATTERN = re.compile(r"[A-Za-z0-9][\w.\-]*\.(?:txt|pdf)", re.IGNORECASE)
TOKEN_PATTERN = re.compile(r"[a-z0-9]+")

app = FastAPI(title="RAGrader integration stub AI")


def embed_text(text: str) -> List[float]:
    vector = [0.0] * DIMENSION
    for token in TOKEN_PATTERN.findall(text.lower()):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        vector[int.from_bytes(digest[:4], "big") % DIMENSION] += 1.0
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


def _flatten(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(_flatten(item) for item in value)
    if isinstance(value, dict):
        return _flatten(value.get("text") or value.get("content") or "")
    return ""


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/v1/embeddings")
async def embeddings(request: Request) -> dict:
    body = await request.json()
    raw: Union[str, List[str]] = body.get("input", "")
    inputs = [raw] if isinstance(raw, str) else list(raw)
    data = [
        {"object": "embedding", "index": i, "embedding": embed_text(_flatten(item))}
        for i, item in enumerate(inputs)
    ]
    return {
        "object": "list",
        "data": data,
        "model": body.get("model", "stub-embed"),
        "usage": {"prompt_tokens": 0, "total_tokens": 0},
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: Request) -> dict:
    body = await request.json()
    prompt = "\n".join(_flatten(m.get("content")) for m in body.get("messages", []))
    sources = list(dict.fromkeys(SOURCE_PATTERN.findall(prompt)))
    grade = {
        "score": 80,
        "feedback": "Stub grade.",
        "criterion_scores": {},
        "citations": [{"text": "stub evidence", "source": s, "page": 1} for s in sources],
        "confidence": 0.85,
    }
    return {
        "id": "chatcmpl-stub",
        "object": "chat.completion",
        "model": body.get("model", "stub"),
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": json.dumps(grade)},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }
