"""Reusable, source-linked knowledge from verified incidents and published FAQ."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from backend.knowledge import bootstrap, vector
from backend.raft.sparse import rank
from backend.storage import sqlite as storage


def signature(domain: str, diagnosis: str) -> str:
    return f"{domain.strip().upper()}:{re.sub(r'\s+', ' ', diagnosis.strip().lower())}"


def corpus_documents() -> list[dict[str, Any]]:
    documents = [item for item in storage.list_knowledge(limit=10000) if item["status"] != "example_pending"]
    faq = storage.list_faq()
    result = []
    for item in documents:
        verified = item["status"] == "resolved"
        example = item["status"] == "example"
        content = f"{item['question']} {item['situation']}"
        if verified or example:
            content += f" {item['diagnosis']} {' '.join(item['actions'])}"
        result.append({"id": item["incident_id"], "type": "incident", "question": item["question"],
                       "answer": item["diagnosis"] if verified or example else "", "actions": item["actions"] if verified or example else [],
                       "status": "example" if example else "verified" if verified else "unverified",
                       "domain": item["domain"], "content": content.strip()})
    for item in faq:
        result.append({"id": f"FAQ-{item['id']}", "type": "faq", "question": item["question"],
                       "answer": item["answer"], "actions": [], "status": "verified",
                       "domain": item["signature"].split(":", 1)[0],
                       "content": f"{item['question']} {item['answer']}"})
    result.extend(bootstrap.documents())
    return result


def search(query: str, limit: int = 5, exclude_id: str | None = None,
           domain: str | None = None, secondary: str | None = None) -> list[dict[str, Any]]:
    if not query.strip():
        return []
    documents = corpus_documents()
    corpus = [item["content"] + " " + item.get("aliases", "") for item in documents]
    try:
        vector.sync(documents, timeout=8)
        dense = vector.scores(query, documents)
    except (OSError, ValueError, KeyError, OverflowError, TypeError):
        dense = {}  # Ollama is optional; lexical search remains available.
    sparse = dict(rank(query, corpus))
    lexical_max = max(sparse.values(), default=0) or 1
    found = []
    for index, item in enumerate(documents):
        if item["id"] == exclude_id:
            continue
        lexical = sparse.get(index, 0) / lexical_max
        semantic = max(0.0, dense.get(item["id"], 0.0))
        if not lexical and semantic < .45:
            continue
        score = .65 * semantic + .35 * lexical if dense else lexical
        if item["status"] == "synthetic":
            score *= .75  # Fictional patterns are hypotheses, not operator-confirmed fixes.
        elif item["status"].startswith("example"):
            score *= .85  # Hypothetical scenarios cannot outrank equally relevant verified resolutions.
        elif item["status"] == "unverified":
            score *= .7  # A question without a confirmed outcome is weaker evidence.
        allowed = {value for value in (domain, secondary) if value and value != "UNKNOWN"}
        if allowed and item.get("domain") not in allowed:
            score *= .3 if item["status"] in ("example", "synthetic", "unverified") else .7
        found.append({key: item[key] for key in ("id", "type", "question", "answer", "actions", "status")} |
                     {"score": round(score, 3), "retrieval": "hybrid" if dense else "lexical"})
    return sorted(found, key=lambda item: item["score"], reverse=True)[:limit]


def frequent_errors(limit: int = 10) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for item in storage.list_knowledge(limit=10000):
        if item["status"] == "example":
            continue
        if not item["diagnosis"]:
            continue
        key = signature(item["domain"], item["diagnosis"])
        row = grouped.setdefault(key, {"signature": key, "domain": item["domain"],
                                      "diagnosis": item["diagnosis"], "count": 0, "resolved": 0,
                                      "latest_at": item["updated_at"], "example_incident_id": item["incident_id"],
                                      "suggested_answer": ""})
        row["count"] += 1
        row["resolved"] += item["status"] == "resolved"
        if item["status"] == "resolved":
            row["example_incident_id"] = item["incident_id"]
            row["suggested_answer"] = "; ".join(item["actions"])
        if item["updated_at"] > row["latest_at"]:
            row["latest_at"] = item["updated_at"]
    published = {item["signature"] for item in storage.list_faq()}
    return [{**row, "faq_published": row["signature"] in published} for row in
            sorted(grouped.values(), key=lambda row: (-row["count"], -row["resolved"], row["diagnosis"]))[:limit]]


def stats() -> dict[str, Any]:
    documents = storage.list_knowledge(limit=10000)
    domains = Counter(item["domain"] for item in documents if not item["status"].startswith("example"))
    return {"questions": sum(not item["status"].startswith("example") for item in documents),
            "resolved_knowledge": sum(item["status"] == "resolved" for item in documents),
            "example_count": sum(item["status"].startswith("example") for item in documents),
            "example_reviewed": sum(item["status"] == "example" for item in documents),
            "faq_count": len(storage.list_faq()), "domains": dict(domains), "vector": vector.status(),
            "bootstrap": bootstrap.status()}
