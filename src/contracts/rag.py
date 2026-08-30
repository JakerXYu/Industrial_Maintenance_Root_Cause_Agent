"""RAG chunk and retrieval contracts."""

from typing import List

from pydantic import BaseModel, Field


class DocumentChunk(BaseModel):
    chunk_id: str
    document: str
    section: str
    text: str
    start_line: int = Field(ge=0)
    end_line: int = Field(ge=0)


class RetrievalResult(BaseModel):
    query: str
    chunks: List[DocumentChunk] = Field(default_factory=list)
