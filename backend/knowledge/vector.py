"""Local Ollama embeddings persisted as compact float32 vectors in SQLite."""

from __future__ import annotations

import hashlib
import json
import math
import os
import struct
import urllib.error
import urllib.request
from typing import Any

from backend.storage import sqlite as storage

MODEL = os.getenv("RAFT_EMBED_MODEL", "qwen3-embedding:0.6b")
OLLAMA_EMBED_URL = os.getenv("OLLAMA_EMBED_URL", "http://127.0.0.1:11434/api/embed")


def embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    body = json.dumps({"model": MODEL, "input": texts, "truncate": True}).encode()
    request = urllib.request.Request(OLLAMA_EMBED_URL, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=45) as response:
        result = json.load(response)
    vectors = result.get("embeddings")
    if not isinstance(vectors, list) or len(vectors) != len(texts) or not all(isinstance(v, list) and v for v in vectors):
        raise ValueError("Invalid Ollama embedding response")
    return vectors


def pack(vector: list[float]) -> bytes:
    if not vector or any(not math.isfinite(value) for value in vector):
        raise ValueError("Invalid embedding values")
    return struct.pack(f"<{len(vector)}f", *vector)


def unpack(blob: bytes, dimensions: int) -> tuple[float, ...]:
    return struct.unpack(f"<{dimensions}f", blob)


def cosine(first: list[float] | tuple[float, ...], second: list[float] | tuple[float, ...]) -> float:
    if len(first) != len(second) or not first:
        return 0.0
    numerator = sum(a * b for a, b in zip(first, second))
    denominator = math.sqrt(sum(a * a for a in first) * sum(b * b for b in second))
    return numerator / denominator if denominator else 0.0


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def sync(documents: list[dict[str, Any]]) -> int:
    """Embed only new or changed documents; keep the original incident data untouched."""
    previous = {row["document_id"]: row for row in storage.list_vectors(MODEL)}
    changed = [doc for doc in documents if doc["id"] not in previous or
               previous[doc["id"]]["content_hash"] != content_hash(doc["content"])]
    for start in range(0, len(changed), 16):
        batch = changed[start:start + 16]
        embeddings = embed([doc["content"][:8000] for doc in batch])
        storage.save_vectors([(doc["id"], MODEL, content_hash(doc["content"]), len(vector), pack(vector))
                              for doc, vector in zip(batch, embeddings)])
    storage.delete_stale_vectors({doc["id"] for doc in documents}, MODEL)
    return len(changed)


def scores(query: str, documents: list[dict[str, Any]]) -> dict[str, float]:
    if not documents:
        return {}
    query_vector = embed([query[:8000]])[0]
    ids = {doc["id"] for doc in documents}
    return {row["document_id"]: cosine(query_vector, unpack(row["embedding"], row["dimensions"]))
            for row in storage.list_vectors(MODEL) if row["document_id"] in ids and row["dimensions"] == len(query_vector)}


def status() -> dict[str, Any]:
    return {"model": MODEL, "indexed": len(storage.list_vectors(MODEL)), "storage": "SQLite float32 vectors"}
