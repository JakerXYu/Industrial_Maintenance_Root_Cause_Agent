"""Deterministic keyword retriever (embedding-free v0)."""

import re
from collections import defaultdict
from typing import Dict, List, Set

from src.contracts.rag import DocumentChunk, RetrievalResult

_TOKEN = re.compile(r"[a-z0-9]+")


class KeywordRetriever:
    def __init__(self, chunks: List[DocumentChunk]):
        self._by_id: Dict[str, DocumentChunk] = {c.chunk_id: c for c in chunks}
        self._index: Dict[str, Set[str]] = defaultdict(set)
        for chunk in chunks:
            for token in _TOKEN.findall(chunk.text.lower()):
                self._index[token].add(chunk.chunk_id)

    def search(self, query: str, top_k: int = 5) -> RetrievalResult:
        query_tokens = set(_TOKEN.findall(query.lower()))
        if not query_tokens:
            return RetrievalResult(query=query, chunks=[])

        scores: Dict[str, int] = defaultdict(int)
        for token in query_tokens:
            for chunk_id in self._index.get(token, set()):
                scores[chunk_id] += 1

        ranked = sorted(scores, key=lambda cid: (-scores[cid], cid))
        chunks = [self._by_id[cid] for cid in ranked[:top_k] if cid in self._by_id]
        return RetrievalResult(query=query, chunks=chunks)
