"""Small local BM25 fallback over resolved incident records."""

from __future__ import annotations

import math
import re
from collections import Counter


def terms(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9_./-]+|[가-힣]+", text.lower())
    result = []
    for word in words:
        result.append(word)
        if re.fullmatch(r"[가-힣]+", word) and len(word) >= 2:
            result.extend(word[index:index + 2] for index in range(len(word) - 1))
    return result


def rank(query: str, documents: list[str]) -> list[tuple[int, float]]:
    if not documents:
        return []
    query_terms = set(terms(query))
    tokenized = [terms(document) for document in documents]
    average = sum(len(doc) for doc in tokenized) / len(tokenized) or 1
    document_frequency = Counter(term for doc in tokenized for term in set(doc))
    scores = []
    for index, doc in enumerate(tokenized):
        frequencies = Counter(doc)
        score = 0.0
        for term in query_terms:
            frequency = frequencies[term]
            if frequency:
                idf = math.log(1 + (len(documents) - document_frequency[term] + .5) / (document_frequency[term] + .5))
                score += idf * frequency * 2.2 / (frequency + 1.2 * (.25 + .75 * len(doc) / average))
        scores.append((index, score))
    return sorted(scores, key=lambda item: item[1], reverse=True)
