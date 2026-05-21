from __future__ import annotations

from dataclasses import dataclass, field

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.indexer.parser_pdf import ParsedSection


@dataclass
class ChunkData:
    chunk_index: int
    text: str
    token_count: int | None
    section_title: str | None
    page_start: int | None
    page_end: int | None
    # Parent-Child markers (added Wave-3 Pkg-PC). Parents are emitted with
    # `is_parent=True` and `parent_chunk_index=None`; children carry the
    # `chunk_index` of their owning parent so the ingest layer can patch the
    # FK after the parent row is flushed and given a primary key.
    is_parent: bool = False
    parent_chunk_index: int | None = None


# Children are the retrieval granularity — small, precise. Parents are the
# generation context — section-sized, wide. Each child belongs to exactly one
# parent. A section produces 1 parent (= whole section, up to PARENT_CHUNK_SIZE)
# plus N children. Sections longer than PARENT_CHUNK_SIZE split into multiple
# parents, each with their own children.
_PARENT_CHUNK_SIZE = 2000
_CHILD_CHUNK_SIZE = 600
_CHILD_CHUNK_OVERLAP = 100


def _splitter(chunk_size: int, chunk_overlap: int) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", "。", ". ", " ", ""],
    )


def _emit_parent_with_children(
    *,
    parent_text: str,
    section_title: str | None,
    page_start: int | None,
    page_end: int | None,
    start_idx: int,
) -> list[ChunkData]:
    """Build one parent followed by its child chunks. Returns the consecutive
    list so the caller can extend a flat chunk array and bump its index."""
    out: list[ChunkData] = []
    parent_idx = start_idx
    out.append(
        ChunkData(
            chunk_index=parent_idx,
            text=parent_text,
            token_count=len(parent_text),
            section_title=section_title,
            page_start=page_start,
            page_end=page_end,
            is_parent=True,
            parent_chunk_index=None,
        )
    )
    next_idx = parent_idx + 1

    if len(parent_text) <= _CHILD_CHUNK_SIZE:
        # Parent fits in a single child window. Emit one child equal to parent
        # so retrieval can still find an embedding for this slice.
        out.append(
            ChunkData(
                chunk_index=next_idx,
                text=parent_text,
                token_count=len(parent_text),
                section_title=section_title,
                page_start=page_start,
                page_end=page_end,
                is_parent=False,
                parent_chunk_index=parent_idx,
            )
        )
        return out

    child_splitter = _splitter(_CHILD_CHUNK_SIZE, _CHILD_CHUNK_OVERLAP)
    for part in child_splitter.split_text(parent_text):
        out.append(
            ChunkData(
                chunk_index=next_idx,
                text=part,
                token_count=len(part),
                section_title=section_title,
                page_start=page_start,
                page_end=page_end,
                is_parent=False,
                parent_chunk_index=parent_idx,
            )
        )
        next_idx += 1
    return out


def split_sections(sections: list[ParsedSection]) -> list[ChunkData]:
    """Two-tier split: parents at section granularity, children at retrieval
    granularity. Children carry parent_chunk_index so persistence can wire FKs."""
    parent_splitter = _splitter(_PARENT_CHUNK_SIZE, 0)
    chunks: list[ChunkData] = []
    idx = 0
    for sec in sections:
        text = sec.text.strip()
        if not text:
            continue
        # Sections beyond the parent cap split into multiple parents. Each
        # spawns its own children — keeps parent context bounded for the LLM.
        parent_texts = (
            [text] if len(text) <= _PARENT_CHUNK_SIZE else parent_splitter.split_text(text)
        )
        for parent_text in parent_texts:
            emitted = _emit_parent_with_children(
                parent_text=parent_text,
                section_title=sec.title,
                page_start=sec.page_start,
                page_end=sec.page_end,
                start_idx=idx,
            )
            chunks.extend(emitted)
            idx += len(emitted)
    return chunks


def split_plain_text(text: str, *, section_title: str | None = None) -> list[ChunkData]:
    """Same two-tier behavior for raw text without parsed sections."""
    parent_splitter = _splitter(_PARENT_CHUNK_SIZE, 0)
    parent_texts = (
        [text] if len(text) <= _PARENT_CHUNK_SIZE else parent_splitter.split_text(text)
    )
    chunks: list[ChunkData] = []
    idx = 0
    for parent_text in parent_texts:
        emitted = _emit_parent_with_children(
            parent_text=parent_text,
            section_title=section_title,
            page_start=None,
            page_end=None,
            start_idx=idx,
        )
        chunks.extend(emitted)
        idx += len(emitted)
    return chunks
