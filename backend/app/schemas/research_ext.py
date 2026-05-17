"""Schemas for v1.3+ research extensions."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class TrendItemPublic(BaseModel):
    id: int
    term: str
    term_type: str
    status: str
    frequency_recent: int
    frequency_baseline: int
    growth_rate: float
    confidence: float
    evidence_document_ids: list[int]
    explanation: str | None


class TrendRunPublic(BaseModel):
    id: int
    topic_id: int
    window_days: int
    bucket: str
    status: str
    summary_md: str | None
    heatmap: dict[str, Any]
    items: list[TrendItemPublic]
    error_message: str | None
    generated_at: datetime | None
    created_at: datetime


class TrendRunSummary(BaseModel):
    id: int
    topic_id: int
    window_days: int
    bucket: str
    status: str
    generated_at: datetime | None
    created_at: datetime


class TrendGenerateResponse(BaseModel):
    status: str
    topic_id: int
    task_id: str | None = None


class TopicTermPublic(BaseModel):
    id: int
    term: str
    normalized_term: str
    term_type: str
    document_count: int
    occurrence_count: int
    first_seen_at: datetime | None
    last_seen_at: datetime | None


class TermDocumentRef(BaseModel):
    document_id: int
    title: str | None
    published_at: datetime | None
    source: str | None


# --- Sprint 2: Claims / Conflicts / Signals ---


class PaperClaimPublic(BaseModel):
    id: int
    document_id: int
    claim_text: str
    claim_type: str
    method: str | None
    dataset: str | None
    metric: str | None
    setting: str | None
    polarity: str
    confidence: float
    evidence_text: str | None


class ClaimDocumentRef(BaseModel):
    document_id: int
    title: str | None


class ConflictRelationPublic(BaseModel):
    id: int
    topic_id: int
    relation_type: str
    confidence: float
    reason_md: str | None
    evidence: dict[str, Any]
    reviewed_by_user: bool
    user_feedback: str | None
    claim_a: PaperClaimPublic
    claim_b: PaperClaimPublic
    document_a: ClaimDocumentRef
    document_b: ClaimDocumentRef


class ConflictDetectResponse(BaseModel):
    status: str
    topic_id: int
    task_id: str | None = None


class ConflictFeedbackBody(BaseModel):
    feedback: str  # "useful" | "dismissed" | "confirmed"


class DocumentSignalPublic(BaseModel):
    id: int
    document_id: int
    document_title: str | None
    signal_type: str
    score: float
    reason_md: str | None
    evidence: dict[str, Any]
    source: str
    detected_at: datetime


class SignalRefreshResponse(BaseModel):
    status: str
    topic_id: int
    task_id: str | None = None


# --- Sprint 3: Hypothesis Verification ---


class HypothesisEvidencePublic(BaseModel):
    id: int
    document_id: int
    document_title: str | None
    chunk_id: int | None
    stance: str
    quote: str | None
    explanation: str | None
    score: float


class HypothesisCheckPublic(BaseModel):
    id: int
    topic_id: int
    hypothesis: str
    status: str
    verdict: str | None
    result_md: str | None
    result_json: dict[str, Any]
    confidence: float
    error_message: str | None
    created_at: datetime
    finished_at: datetime | None
    evidence: list[HypothesisEvidencePublic] = []


class HypothesisCheckCreate(BaseModel):
    hypothesis: str


class HypothesisCheckSummary(BaseModel):
    id: int
    topic_id: int
    hypothesis: str
    status: str
    verdict: str | None
    confidence: float
    created_at: datetime
    finished_at: datetime | None


# --- Sprint 4: Comparison + Writing ---


class ComparisonCreate(BaseModel):
    title: str
    document_ids: list[int]


class ComparisonItemPublic(BaseModel):
    document_id: int
    role: str
    order_index: int


class ComparisonSessionSummary(BaseModel):
    id: int
    topic_id: int
    title: str
    status: str
    document_ids: list[int]
    created_at: datetime
    finished_at: datetime | None


class ComparisonSessionPublic(BaseModel):
    id: int
    topic_id: int
    title: str
    status: str
    result_md: str | None
    result_json: dict[str, Any]
    error_message: str | None
    items: list[ComparisonItemPublic]
    created_at: datetime
    finished_at: datetime | None


class WritingProjectCreate(BaseModel):
    title: str
    user_intent: str
    document_ids: list[int]


class WritingProjectSummary(BaseModel):
    id: int
    topic_id: int
    title: str
    writing_type: str
    status: str
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class WritingProjectPublic(BaseModel):
    id: int
    topic_id: int
    title: str
    writing_type: str
    user_intent: str | None
    status: str
    scope_json: dict[str, Any]
    outline_json: dict[str, Any]
    draft_md: str | None
    citation_json: list[dict[str, Any]]
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    document_ids: list[int] = []


# --- Sprint 5: Graph + Glossary + Export ---


class GraphNode(BaseModel):
    id: int
    title: str | None
    year: int | None
    source: str | None


class GraphEdge(BaseModel):
    source: int
    target: int
    type: str
    weight: float
    evidence: dict[str, Any]


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class GraphRebuildResponse(BaseModel):
    status: str
    edges: int
    nodes: int


class GlossaryTermPublic(BaseModel):
    id: int
    term: str
    normalized_term: str
    definition: str | None
    representative_document_ids: list[int]
    confidence: float


class GlossaryGenerateResponse(BaseModel):
    status: str
    generated: int
    skipped: int


class ExportPayload(BaseModel):
    export_type: str
    content: str
    char_count: int
