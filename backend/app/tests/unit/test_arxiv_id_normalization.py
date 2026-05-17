from __future__ import annotations

from app.collectors.arxiv_collector import ArxivCollector


def test_normalize_id_strips_url_and_version():
    assert ArxivCollector._normalize_id("http://arxiv.org/abs/2401.12345v3") == "2401.12345"
    assert ArxivCollector._normalize_id("2401.12345") == "2401.12345"
    assert ArxivCollector._normalize_id("cs.CV/0301001v1") == "cs.CV/0301001"
