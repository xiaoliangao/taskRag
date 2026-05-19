"""Unit tests for export_service formatting (Sprint 5)."""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from app.services.export_service import (
    _authors_str,
    _bibtex_one,
    _first_author_last,
    _md_one,
    _slug,
    _year,
)


def _doc(**overrides) -> SimpleNamespace:
    base = dict(
        id=1,
        source="arxiv",
        external_id="2401.12345",
        title="A Wonderful Paper About Stereo Matching",
        authors=["Alice Smith", "Bob Lee"],
        published_at=datetime(2024, 6, 1, tzinfo=UTC),
        url="https://arxiv.org/abs/2401.12345",
        abstract="abc",
        pdf_path=None,
        full_text_path=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_slug_handles_unicode_and_punctuation():
    assert _slug("Hello, World!") == "hello-world"
    assert _slug(None) == "item"
    assert _slug("    ") == "item"


def test_year_falls_back_to_nd_when_missing():
    assert _year(_doc(published_at=None)) == "n.d."
    assert _year(_doc(published_at=datetime(2023, 1, 1, tzinfo=UTC))) == "2023"


def test_authors_str_joins_with_and():
    s = _authors_str(_doc(authors=["A B", "C D", "E F"]))
    assert s == "A B and C D and E F"


def test_authors_str_handles_dict_authors():
    s = _authors_str(_doc(authors=[{"name": "X Y"}, {"name": "Z W"}]))
    assert s == "X Y and Z W"


def test_authors_str_empty_returns_unknown():
    assert _authors_str(_doc(authors=[])) == "Unknown"


def test_first_author_last_picks_last_token():
    assert _first_author_last(_doc(authors=["Alice Smith"])) == "Smith"
    assert _first_author_last(_doc(authors=[{"name": "Bob Lee"}])) == "Lee"
    assert _first_author_last(_doc(authors=[])) == "anon"


def test_bibtex_one_for_arxiv_has_eprint_and_archive():
    out = _bibtex_one(_doc())
    assert out.startswith("@article{")
    assert "archivePrefix = {arXiv}" in out
    assert "eprint = {2401.12345}" in out
    assert "title = {A Wonderful Paper About Stereo Matching}" in out
    assert "year = {2024}" in out


def test_bibtex_one_for_upload_is_misc():
    out = _bibtex_one(_doc(source="upload", external_id="abc"))
    assert out.startswith("@misc{")
    assert "archivePrefix" not in out


def test_md_one_yaml_frontmatter_escapes_quotes():
    md = _md_one(_doc(title='Some "Quoted" Title'), briefing=None)
    assert md.startswith("---\n")
    assert 'title: "Some \\"Quoted\\" Title"' in md
    # No frontmatter braces; fallback abstract section is present
    assert "## Abstract" in md
