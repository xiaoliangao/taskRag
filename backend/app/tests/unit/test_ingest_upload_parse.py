from __future__ import annotations

from types import SimpleNamespace

from app.collectors.base import RawDocument
from app.indexer import ingest_service
from app.indexer.parser_pdf import ParsedPdf, ParsedSection


def _fake_settings(tmp_path):
    return SimpleNamespace(
        fulltext_storage_dir=tmp_path,
        fulltext_max_bytes=1_000_000,
    )


def _upload_raw(pdf_path) -> RawDocument:
    return RawDocument(
        source="upload",
        external_id="upload-abc123",
        title="Uploaded PDF",
        authors=[],
        url="local://paper.pdf",
        abstract=None,
        matched_keyword="upload",
        metadata={"local_path": str(pdf_path), "original_filename": "paper.pdf"},
    )


def test_uploaded_pdf_is_parsed_into_chunks(tmp_path, monkeypatch):
    """Regression: uploads used to fall through to the empty abstract fallback
    and silently SKIP. They must now be parsed from local_path into chunks."""
    monkeypatch.setattr(ingest_service, "get_settings", lambda: _fake_settings(tmp_path))

    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")

    parsed = ParsedPdf(
        full_text="Introduction\n" + ("This paper studies retrieval augmented generation. " * 60),
        sections=[
            ParsedSection(
                title="Introduction",
                text="This paper studies retrieval augmented generation. " * 60,
                page_start=1,
                page_end=2,
            )
        ],
    )
    monkeypatch.setattr(ingest_service, "parse_pdf", lambda p, content_hash=None: parsed)

    document = SimpleNamespace(
        source="upload",
        external_id="upload-abc123",
        title="Uploaded PDF",
        content_hash="hash",
        metadata_json={},
        pdf_path=None,
    )

    chunks, fulltext_path = ingest_service._parse_to_chunks(document, _upload_raw(pdf_path))

    assert len(chunks) > 0, "uploaded PDF must produce chunks, not SKIP"
    assert document.metadata_json.get("abstract_only") is False
    assert document.pdf_path == str(pdf_path)
    assert fulltext_path is not None


def test_uploaded_pdf_unparseable_falls_back_to_abstract_only(tmp_path, monkeypatch):
    """When PyMuPDF can't extract text we degrade to abstract-only (empty for
    uploads → SKIP), but must NOT crash and must stamp abstract_only=True."""
    monkeypatch.setattr(ingest_service, "get_settings", lambda: _fake_settings(tmp_path))

    pdf_path = tmp_path / "scanned.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    monkeypatch.setattr(ingest_service, "parse_pdf", lambda p, content_hash=None: None)

    document = SimpleNamespace(
        source="upload",
        external_id="upload-deadbeef",
        title="Scanned PDF",
        content_hash="hash",
        metadata_json={},
        pdf_path=None,
    )

    chunks, fulltext_path = ingest_service._parse_to_chunks(document, _upload_raw(pdf_path))

    assert chunks == []
    assert fulltext_path is None
    assert document.metadata_json.get("abstract_only") is True
