"""Tests for RAG chunking and retrieval."""

from pathlib import Path

from src.contracts.rag import DocumentChunk
from src.rag.chunking import chunk_markdown, load_documents
from src.rag.retriever import KeywordRetriever


def test_chunk_markdown_heading_aware():
    text = "# Intro\n\nFirst paragraph about lubrication.\n\n## Safety\n\nLock out the drive.\n"
    chunks = chunk_markdown(text, document="manual", target_chars=1000, overlap_chars=100)
    assert chunks
    sections = {c.section for c in chunks}
    assert "Intro" in sections
    assert "Safety" in sections
    assert all(c.text.strip() for c in chunks)
    assert all(c.chunk_id.startswith("manual:") for c in chunks)


def test_load_documents():
    docs_dir = Path(__file__).resolve().parents[1] / "data" / "docs"
    chunks = load_documents(docs_dir)
    assert chunks
    assert all(isinstance(c, DocumentChunk) for c in chunks)
    assert all(c.text.strip() for c in chunks)


def test_keyword_retriever_returns_relevant_chunk():
    chunks = [
        DocumentChunk(
            chunk_id="manual:000",
            document="manual",
            section="Lubrication",
            text="Lubrication must be checked every 30 days to avoid friction.",
            start_line=0,
            end_line=1,
        ),
        DocumentChunk(
            chunk_id="safety:000",
            document="safety",
            section="Lockout",
            text="Always isolate energy before maintenance.",
            start_line=0,
            end_line=1,
        ),
    ]
    retriever = KeywordRetriever(chunks)
    result = retriever.search("lubrication friction", top_k=1)
    assert result.chunks
    assert result.chunks[0].chunk_id == "manual:000"
