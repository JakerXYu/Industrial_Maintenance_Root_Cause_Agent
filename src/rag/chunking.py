"""Heading-aware Markdown chunking."""

from pathlib import Path
from typing import List

from src.contracts.rag import DocumentChunk


def _split_long(text: str, target_chars: int, overlap_chars: int) -> List[str]:
    if len(text) <= target_chars:
        return [text]
    pieces: List[str] = []
    start = 0
    while start < len(text):
        end = min(start + target_chars, len(text))
        pieces.append(text[start:end])
        if end == len(text):
            break
        start = max(end - overlap_chars, start + 1)
    return pieces


def chunk_markdown(
    text: str,
    document: str,
    target_chars: int = 1200,
    overlap_chars: int = 200,
) -> List[DocumentChunk]:
    """Split markdown into sections, then into overlapping chunks within sections."""
    lines = text.splitlines()
    sections = []
    current_section = "(intro)"
    current_start = 0
    current_lines: List[str] = []

    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            sections.append((current_section, current_start, i, "\n".join(current_lines)))
            current_section = stripped.lstrip("#").strip() or "(unnamed)"
            current_start = i
            current_lines = [line]
        else:
            current_lines.append(line)
    sections.append((current_section, current_start, len(lines), "\n".join(current_lines)))

    chunks: List[DocumentChunk] = []
    idx = 0
    for section, start_line, end_line, content in sections:
        content = content.strip()
        if not content:
            continue
        for piece in _split_long(content, target_chars, overlap_chars):
            chunks.append(
                DocumentChunk(
                    chunk_id=f"{document}:{idx:03d}",
                    document=document,
                    section=section,
                    text=piece,
                    start_line=start_line,
                    end_line=end_line,
                )
            )
            idx += 1
    return chunks


def load_documents(
    docs_dir: Path,
    target_chars: int = 1200,
    overlap_chars: int = 200,
) -> List[DocumentChunk]:
    chunks: List[DocumentChunk] = []
    for path in sorted(Path(docs_dir).glob("*.md")):
        text = path.read_text(encoding="utf-8")
        chunks.extend(
            chunk_markdown(
                text,
                document=path.stem,
                target_chars=target_chars,
                overlap_chars=overlap_chars,
            )
        )
    return chunks
