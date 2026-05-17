from __future__ import annotations

from dataclasses import dataclass

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


_DEFAULT_CHUNK_SIZE = 800
_DEFAULT_CHUNK_OVERLAP = 100


def _splitter(chunk_size: int = _DEFAULT_CHUNK_SIZE, chunk_overlap: int = _DEFAULT_CHUNK_OVERLAP) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", "。", ". ", " ", ""],
    )


def split_sections(sections: list[ParsedSection]) -> list[ChunkData]:
    """Split parsed sections into chunks, prefer keeping a section together if it fits."""
    splitter = _splitter()
    chunks: list[ChunkData] = []
    idx = 0
    for sec in sections:
        text = sec.text.strip()
        if not text:
            continue
        if len(text) <= _DEFAULT_CHUNK_SIZE:
            chunks.append(
                ChunkData(
                    chunk_index=idx,
                    text=text,
                    token_count=len(text),
                    section_title=sec.title,
                    page_start=sec.page_start,
                    page_end=sec.page_end,
                )
            )
            idx += 1
        else:
            for part in splitter.split_text(text):
                chunks.append(
                    ChunkData(
                        chunk_index=idx,
                        text=part,
                        token_count=len(part),
                        section_title=sec.title,
                        page_start=sec.page_start,
                        page_end=sec.page_end,
                    )
                )
                idx += 1
    return chunks


def split_plain_text(text: str, *, section_title: str | None = None) -> list[ChunkData]:
    splitter = _splitter()
    parts = splitter.split_text(text)
    return [
        ChunkData(
            chunk_index=i,
            text=p,
            token_count=len(p),
            section_title=section_title,
            page_start=None,
            page_end=None,
        )
        for i, p in enumerate(parts)
    ]
