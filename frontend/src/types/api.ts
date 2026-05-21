export interface UserPublic {
  id: number;
  email: string;
  created_at: string;
  is_admin?: boolean;
}

export interface UserMe {
  id: number;
  email: string;
  settings: Record<string, unknown>;
  is_admin?: boolean;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: UserPublic;
}

export interface Topic {
  id: number;
  name: string;
  description: string | null;
  keywords: string[];
  sources: string[];
  schedule_type: string;
  schedule_time: string;
  max_results_per_source_per_run: number;
  enabled: boolean;
  document_count: number;
  last_collected_at: string | null;
  created_at: string;
}

export interface DocumentSummary {
  id: number;
  source: string;
  title: string;
  authors: string[];
  published_at: string | null;
  url: string;
  abstract: string | null;
  matched_keyword: string | null;
  added_at: string;
  reading_priority?: "high" | "medium" | "low" | null;
  relevance_score?: number | null;
}

export interface DocumentChunkPublic {
  id: number;
  chunk_index: number;
  section_title: string | null;
  page_start: number | null;
  page_end: number | null;
  text: string;
}

export interface DocumentDetail {
  id: number;
  source: string;
  title: string;
  authors: string[];
  published_at: string | null;
  url: string;
  abstract: string | null;
  full_text: string | null;
  chunks: DocumentChunkPublic[];
}

export interface DocumentListResponse {
  items: DocumentSummary[];
  page: number;
  page_size: number;
  total: number;
}

export interface TaskProgress {
  step?: string | null;          // searching / ingesting / done
  total?: number | null;
  processed?: number | null;
  current_doc?: string | null;
  current_title?: string | null;
  new?: number | null;
  reused?: number | null;
  skipped?: number | null;
  last_error?: string | null;
}

export interface TaskItem {
  id: number;
  topic_id: number;
  source: string;
  trigger: string;
  status: string;
  new_docs_count: number;
  reused_docs_count: number;
  skipped_docs_count: number;
  started_at: string | null;
  finished_at: string | null;
  error_msg: string | null;
  created_at: string;
  progress?: TaskProgress | null;
}

export interface TaskListResponse {
  items: TaskItem[];
  total: number;
}

export interface NotificationItem {
  id: number;
  type: string;
  title: string;
  body: string;
  payload: Record<string, unknown>;
  read_at: string | null;
  created_at: string;
}

export interface NotificationListResponse {
  items: NotificationItem[];
  total: number;
  unread_count: number;
}

export interface Citation {
  document_id: number;
  chunk_id: number | null;
  title: string;
  url: string;
  source: string;
  published_at: string | null;
  section_title: string | null;
  page_start: number | null;
  page_end: number | null;
  score: number;
}

export interface ChatSession {
  id: number;
  topic_id: number;
  title: string;
  mode?: string;
  created_at: string;
}

export interface ChatMessage {
  id: number;
  session_id: number;
  role: "user" | "assistant" | "system";
  content: string;
  citations: Citation[];
  created_at: string;
}

export interface SettingsPublic {
  timezone: string;
  email_notifications_enabled: boolean;
  preferred_llm_provider: string;
  preferred_llm_model: string;
  preferred_embedding_provider: string;
}

export interface ApiError {
  error: { code: string; message: string; details?: Record<string, unknown> };
}

// --- v1.1+ Intelligence Layer ---

export interface BriefingPublic {
  status: string;
  language: string;
  one_sentence_summary: string | null;
  problem: string | null;
  method: string | null;
  contributions: string[];
  experiments: string[];
  limitations: string[];
  datasets: string[];
  metrics: string[];
  code_available: boolean | null;
  code_url: string | null;
  reading_time_minutes: number | null;
  evidence_chunk_ids: number[];
  generated_at: string | null;
}

export interface TopicInsightPublic {
  relevance_score: number | null;
  relevance_reason: string | null;
  reading_priority: "high" | "medium" | "low" | null;
  why_read: string | null;
  tags: string[];
}

export interface UserDocStatePublic {
  status: "unread" | "reading" | "read" | "archived";
  favorite: boolean;
  rating: number | null;
  personal_note: string | null;
  tags: string[];
  last_opened_at: string | null;
}

export interface DocumentBriefingResponse {
  document_id: number;
  title: string;
  briefing: BriefingPublic | null;
  topic_insight: TopicInsightPublic | null;
  user_state: UserDocStatePublic | null;
}

export interface TopicPulse {
  id: number;
  topic_id: number;
  pulse_date: string;
  status: string;
  title: string | null;
  summary_md: string | null;
  highlights: Array<{ type?: string; text: string; document_id?: number; term?: string }>;
  new_documents: Array<{ document_id: number; title: string }>;
  important_documents: Array<{ document_id: number; title: string; reason?: string }>;
  emerging_keywords: Array<{ term: string; score?: number }>;
  suggested_actions: Array<{ action: string; question?: string; document_id?: number; reason?: string }>;
  citations: any[];
  generated_at: string | null;
}

export interface ReadingPathItemPublic {
  id: number;
  document_id: number;
  document_title: string;
  order_index: number;
  stage: string | null;
  reason: string | null;
  expected_minutes: number | null;
  prerequisite_document_ids: number[];
  user_status?: string;
}

export interface ReadingPathPublic {
  id: number;
  topic_id: number;
  title: string;
  description: string | null;
  status: string;
  generated_at: string | null;
  items: ReadingPathItemPublic[];
}

export interface ResearchInsight {
  id: number;
  topic_id: number;
  insight_type: string;
  status: string;
  title: string;
  summary: string | null;
  detail_md: string | null;
  confidence: number | null;
  evidence_document_ids: number[];
  evidence_chunk_ids: number[];
  suggested_questions: string[];
  suggested_experiments: string[];
  generated_at: string | null;
}

export interface ResearchNote {
  id: number;
  user_id: number;
  topic_id: number;
  source_type: string;
  source_id: number | null;
  title: string | null;
  content_md: string;
  tags: string[];
  pinned: boolean;
  created_at: string;
  updated_at: string;
}

// --- v1.3+ Trend Radar ---

export type TrendItemStatus = "emerging" | "rising" | "stable" | "declining";

export interface TrendItem {
  id: number;
  term: string;
  term_type: string;
  status: TrendItemStatus | string;
  frequency_recent: number;
  frequency_baseline: number;
  growth_rate: number;
  confidence: number;
  evidence_document_ids: number[];
  explanation: string | null;
}

export interface TrendHeatmap {
  buckets: string[];
  terms: string[];
  values: number[][];
}

export interface TrendRunPublic {
  id: number;
  topic_id: number;
  window_days: number;
  bucket: string;
  status: string;
  summary_md: string | null;
  heatmap: TrendHeatmap | Record<string, never>;
  items: TrendItem[];
  error_message: string | null;
  generated_at: string | null;
  created_at: string;
}

export interface TrendRunSummary {
  id: number;
  topic_id: number;
  window_days: number;
  bucket: string;
  status: string;
  generated_at: string | null;
  created_at: string;
}

export interface TrendGenerateResponse {
  status: string;
  topic_id: number;
  task_id?: string | null;
}

export interface TopicTermPublic {
  id: number;
  term: string;
  normalized_term: string;
  term_type: string;
  document_count: number;
  occurrence_count: number;
  first_seen_at: string | null;
  last_seen_at: string | null;
}

export interface TermDocumentRef {
  document_id: number;
  title: string | null;
  published_at: string | null;
  source: string | null;
}

// --- v1.3 Sprint 2: Claims / Conflicts / Signals ---

export interface PaperClaimPublic {
  id: number;
  document_id: number;
  claim_text: string;
  claim_type: string;
  method: string | null;
  dataset: string | null;
  metric: string | null;
  setting: string | null;
  polarity: string;
  confidence: number;
  evidence_text: string | null;
}

export interface ClaimDocumentRef {
  document_id: number;
  title: string | null;
}

export interface ConflictRelationPublic {
  id: number;
  topic_id: number;
  relation_type: "supports" | "conflicts" | "qualifies" | "insufficient_info" | string;
  confidence: number;
  reason_md: string | null;
  evidence: Record<string, unknown>;
  reviewed_by_user: boolean;
  user_feedback: string | null;
  claim_a: PaperClaimPublic;
  claim_b: PaperClaimPublic;
  document_a: ClaimDocumentRef;
  document_b: ClaimDocumentRef;
}

export interface ConflictDetectResponse {
  status: string;
  topic_id: number;
  task_id?: string | null;
}

export interface DocumentSignalPublic {
  id: number;
  document_id: number;
  document_title: string | null;
  signal_type: string;
  score: number;
  reason_md: string | null;
  evidence: Record<string, unknown>;
  source: string;
  detected_at: string;
}

export interface SignalRefreshResponse {
  status: string;
  topic_id: number;
  task_id?: string | null;
}

// --- v1.3 Sprint 3: Hypothesis + Chat modes ---

export type HypothesisStance = "support" | "oppose" | "qualify" | "neutral";

export interface HypothesisEvidencePublic {
  id: number;
  document_id: number;
  document_title: string | null;
  chunk_id: number | null;
  stance: HypothesisStance | string;
  quote: string | null;
  explanation: string | null;
  score: number;
}

export interface HypothesisCheckPublic {
  id: number;
  topic_id: number;
  hypothesis: string;
  status: string;
  verdict: string | null;
  result_md: string | null;
  result_json: Record<string, unknown>;
  confidence: number;
  error_message: string | null;
  created_at: string;
  finished_at: string | null;
  evidence: HypothesisEvidencePublic[];
}

export interface HypothesisCheckSummary {
  id: number;
  topic_id: number;
  hypothesis: string;
  status: string;
  verdict: string | null;
  confidence: number;
  created_at: string;
  finished_at: string | null;
}

export type ChatMode = "default" | "mentor" | "beginner" | "debate" | "reviewer" | "what_if";

// --- v1.3 Sprint 4: Comparison + Writing ---

export interface ComparisonItemPublic {
  document_id: number;
  role: string;
  order_index: number;
}

export interface ComparisonSessionSummary {
  id: number;
  topic_id: number;
  title: string;
  status: string;
  document_ids: number[];
  created_at: string;
  finished_at: string | null;
}

export interface ComparisonSessionPublic {
  id: number;
  topic_id: number;
  title: string;
  status: string;
  result_md: string | null;
  result_json: {
    columns?: string[];
    rows?: Array<Record<string, string | number>>;
  };
  error_message: string | null;
  items: ComparisonItemPublic[];
  created_at: string;
  finished_at: string | null;
}

export interface WritingProjectSummary {
  id: number;
  topic_id: number;
  title: string;
  writing_type: string;
  status: string;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

// --- v1.3 Sprint 5: Graph + Glossary + Export ---

export interface GraphNode {
  id: number;
  title: string | null;
  year: number | null;
  source: string | null;
}

export interface GraphEdge {
  source: number;
  target: number;
  type: string;
  weight: number;
  evidence: Record<string, unknown>;
}

export interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface GlossaryTermPublic {
  id: number;
  term: string;
  normalized_term: string;
  definition: string | null;
  representative_document_ids: number[];
  confidence: number;
}

export interface ExportPayload {
  export_type: string;
  content: string;
  char_count: number;
}

export interface WritingProjectPublic {
  id: number;
  topic_id: number;
  title: string;
  writing_type: string;
  user_intent: string | null;
  status: string;
  scope_json: Record<string, unknown>;
  outline_json: Record<string, unknown>;
  draft_md: string | null;
  citation_json: Array<{
    label: string;
    document_id: number;
    title?: string;
    url?: string;
  }>;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  document_ids: number[];
}
