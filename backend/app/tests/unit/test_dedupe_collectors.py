from __future__ import annotations

from app.collectors.base import RawDocument, _normalize_title, dedupe_raw_docs


def test_dedupe_by_source_external_id_keeps_first_and_collects_keywords():
    items = [
        RawDocument(source="arxiv", external_id="2401.00001", title="A", url="u", matched_keyword="rag"),
        RawDocument(source="arxiv", external_id="2401.00001", title="A", url="u", matched_keyword="reranker"),
        RawDocument(source="arxiv", external_id="2401.00002", title="B", url="u2", matched_keyword="rag"),
    ]
    out = dedupe_raw_docs(items)
    assert len(out) == 2
    first = next(d for d in out if d.external_id == "2401.00001")
    assert set(first.metadata.get("all_matched_keywords", [])) == {"rag", "reranker"}
    # matched_keyword stays as the first one
    assert first.matched_keyword == "rag"


def test_dedupe_empty_returns_empty():
    assert dedupe_raw_docs([]) == []


def test_normalize_title_strips_punct_and_whitespace():
    a = _normalize_title("Object Detection: A Survey.")
    b = _normalize_title("object  detection  a  survey")
    assert a == b


def test_dedupe_falls_back_to_normalized_title_when_ids_differ():
    """OpenAlex sometimes emits the same paper with different external_ids
    across pages; we still want one row in the UI."""
    items = [
        RawDocument(
            source="openalex",
            external_id="W111",
            title="信息空间本体论:锁定度假说及其跨数据库符号定理验证",
            url="u1",
            matched_keyword="目标检测",
        ),
        RawDocument(
            source="openalex",
            external_id="W222",  # different id, same paper
            title="信息空间本体论:锁定度假说及其跨数据库符号定理验证",
            url="u1",
            matched_keyword="目标检测",
        ),
    ]
    out = dedupe_raw_docs(items)
    assert len(out) == 1
    assert out[0].external_id == "W111"  # first one wins


def test_dedupe_does_not_collapse_distinct_papers_with_similar_titles():
    """Whitespace/punct equality must still discriminate when content differs."""
    items = [
        RawDocument(source="arxiv", external_id="a", title="Object Detection v1", url="u"),
        RawDocument(source="arxiv", external_id="b", title="Object Detection v2", url="u"),
    ]
    out = dedupe_raw_docs(items)
    assert len(out) == 2
