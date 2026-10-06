"""Reusable, source-linked knowledge from verified incidents and published FAQ."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from backend.raft.sparse import rank
from backend.storage import sqlite as storage


def signature(domain: str, diagnosis: str) -> str:
    return f"{domain.strip().upper()}:{re.sub(r'\s+', ' ', diagnosis.strip().lower())}"


def search(query: str, limit: int = 5) -> list[dict[str, Any]]:
    documents = storage.list_knowledge("resolved")
    faq = storage.list_faq()
    corpus = [f"{item['question']} {item['situation']} {item['diagnosis']}" for item in documents]
    corpus += [f"{item['question']} {item['answer']}" for item in faq]
    found = []
    for index, score in rank(query, corpus):
        if score <= 0:
            continue
        if index < len(documents):
            item = documents[index]
            found.append({"id": item["incident_id"], "type": "incident", "question": item["question"],
                          "answer": item["diagnosis"], "actions": item["actions"], "score": round(score, 3)})
        else:
            item = faq[index - len(documents)]
            found.append({"id": f"FAQ-{item['id']}", "type": "faq", "question": item["question"],
                          "answer": item["answer"], "actions": [], "score": round(score, 3)})
        if len(found) >= limit:
            break
    return found


def frequent_errors(limit: int = 10) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for item in storage.list_knowledge(limit=10000):
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
    domains = Counter(item["domain"] for item in documents)
    return {"questions": len(documents), "resolved_knowledge": sum(item["status"] == "resolved" for item in documents),
            "faq_count": len(storage.list_faq()), "domains": dict(domains)}
