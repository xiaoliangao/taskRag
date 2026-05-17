"""Rule-based term extraction for Trend Radar (Sprint 1)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

_PATTERNS = [
    # CamelCase / hyphenated tech names: RAFT-Stereo, DINO-v2, RAFT_Stereo
    re.compile(r"\b[A-Z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+)+\b"),
    # All-caps acronyms or model names: RAG, MVSNet, LoRA, BERT, GPT4
    re.compile(r"\b[A-Z]{2,}[A-Za-z0-9]*\b"),
    # 1-3 word phrase ending with a known tech suffix
    re.compile(
        r"\b(?:[a-z][a-z0-9]*\s+){0,3}"
        r"(?:matching|estimation|attention|transformer|diffusion|retrieval|"
        r"reranking|alignment|embedding|tokenization|compression|distillation|"
        r"pretraining|finetuning|reasoning)\b",
        re.IGNORECASE,
    ),
]

_STOPWORDS = {
    "paper", "method", "model", "models", "result", "results", "dataset", "datasets",
    "approach", "approaches", "framework", "frameworks", "study", "studies",
    "the", "and", "for", "with", "using", "from", "this", "that", "based",
    "novel", "new", "state", "art", "art's", "first", "second", "third",
    "introduction", "abstract", "conclusion", "section", "table", "figure",
}

_MIN_TERM_LEN = 2
_MAX_TERM_LEN = 64


def normalize_term(term: str) -> str:
    return re.sub(r"\s+", " ", term.strip().lower())


def _is_acceptable(term: str) -> bool:
    s = term.strip()
    if not s:
        return False
    if len(s) < _MIN_TERM_LEN or len(s) > _MAX_TERM_LEN:
        return False
    if s.isdigit():
        return False
    lower = s.lower()
    if lower in _STOPWORDS:
        return False
    if all(ch in ".,;:-_" or ch.isdigit() for ch in s):
        return False
    return True


def _classify_term(term: str) -> str:
    """Light heuristic classification. LLM pass can refine later."""
    t = term.strip()
    lower = t.lower()
    if any(lower.endswith(s) for s in (" estimation", " matching", " attention",
                                       " transformer", " diffusion", " retrieval",
                                       " reranking", " alignment", " embedding",
                                       " pretraining", " finetuning", " reasoning",
                                       " distillation", " compression",
                                       " tokenization")):
        return "method"
    if t.isupper() and 2 <= len(t) <= 8:
        return "model"
    if re.match(r"^[A-Z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+)+$", t):
        return "method"
    return "keyword"


@dataclass(frozen=True)
class CandidateTerm:
    term: str
    normalized: str
    term_type: str
    source_field: str
    context_text: str | None


def _iter_text_candidates(text: str, source_field: str) -> Iterable[CandidateTerm]:
    if not text:
        return
    seen: set[str] = set()
    for pattern in _PATTERNS:
        for match in pattern.finditer(text):
            term = match.group(0).strip().strip(".,;:")
            if not _is_acceptable(term):
                continue
            norm = normalize_term(term)
            if norm in seen:
                continue
            seen.add(norm)
            start = max(0, match.start() - 40)
            end = min(len(text), match.end() + 40)
            yield CandidateTerm(
                term=term,
                normalized=norm,
                term_type=_classify_term(term),
                source_field=source_field,
                context_text=text[start:end].strip(),
            )


def extract_candidates_for_document(
    *,
    title: str | None,
    abstract: str | None,
    briefing_method: str | None = None,
    briefing_contributions: list | None = None,
    briefing_datasets: list | None = None,
    briefing_metrics: list | None = None,
    insight_why_read: str | None = None,
) -> list[CandidateTerm]:
    """Collect candidate terms from a document's structured fields."""
    out: list[CandidateTerm] = []
    seen: set[tuple[str, str]] = set()

    def _add(text: str | None, source_field: str) -> None:
        if not text:
            return
        for cand in _iter_text_candidates(text, source_field):
            key = (cand.normalized, source_field)
            if key in seen:
                continue
            seen.add(key)
            out.append(cand)

    _add(title, "title")
    _add(abstract, "abstract")
    _add(briefing_method, "method")

    for contrib in briefing_contributions or []:
        if isinstance(contrib, str):
            _add(contrib, "contributions")
        elif isinstance(contrib, dict):
            for v in contrib.values():
                if isinstance(v, str):
                    _add(v, "contributions")

    for ds in briefing_datasets or []:
        if isinstance(ds, str):
            _add(ds, "datasets")
            # also accept raw dataset names as terms (uppercase-ish)
            if _is_acceptable(ds):
                norm = normalize_term(ds)
                key = (norm, "datasets")
                if key not in seen:
                    seen.add(key)
                    out.append(CandidateTerm(
                        term=ds.strip(),
                        normalized=norm,
                        term_type="dataset",
                        source_field="datasets",
                        context_text=None,
                    ))
        elif isinstance(ds, dict):
            name = ds.get("name") or ds.get("dataset") or ""
            if name:
                norm = normalize_term(name)
                key = (norm, "datasets")
                if key not in seen:
                    seen.add(key)
                    out.append(CandidateTerm(
                        term=name,
                        normalized=norm,
                        term_type="dataset",
                        source_field="datasets",
                        context_text=None,
                    ))

    for m in briefing_metrics or []:
        if isinstance(m, str):
            _add(m, "metrics")
            if _is_acceptable(m):
                norm = normalize_term(m)
                key = (norm, "metrics")
                if key not in seen:
                    seen.add(key)
                    out.append(CandidateTerm(
                        term=m.strip(),
                        normalized=norm,
                        term_type="metric",
                        source_field="metrics",
                        context_text=None,
                    ))
        elif isinstance(m, dict):
            name = m.get("name") or m.get("metric") or ""
            if name:
                norm = normalize_term(name)
                key = (norm, "metrics")
                if key not in seen:
                    seen.add(key)
                    out.append(CandidateTerm(
                        term=name,
                        normalized=norm,
                        term_type="metric",
                        source_field="metrics",
                        context_text=None,
                    ))

    _add(insight_why_read, "why_read")
    return out
