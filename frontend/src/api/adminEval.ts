import { client } from "./client";

export interface EvalRunSummary {
  id: number;
  topic_id: number;
  label: string;
  commit_sha: string | null;
  created_at: string;
  recall_at_5: number | null;
  recall_at_20: number | null;
  mrr: number | null;
  n_questions: number;
}

export interface PerQuestionRow {
  question_id: number;
  question: string;
  tag: string | null;
  expected: number;
  retrieved: number;
  "recall@5": number;
  [k: string]: unknown;
}

export interface EvalRunDetail extends EvalRunSummary {
  notes: string | null;
  metrics_json: {
    n_questions?: number;
    "recall@5"?: number;
    "recall@20"?: number;
    mrr?: number;
    per_tag?: Record<string, Record<string, number>>;
    per_question?: PerQuestionRow[];
  };
}

export interface EvalQuestion {
  id: number;
  topic_id: number;
  question: string;
  reference_answer: string | null;
  expected_chunk_ids: number[];
  tag: string | null;
  created_at: string;
}

export interface TriggerRunRequest {
  topic_id: number;
  label?: string;
  notes?: string;
}

export interface TriggerRunResponse {
  run_id: number;
  label: string;
  metrics: EvalRunDetail["metrics_json"];
}

export async function listEvalRuns(topicId?: number): Promise<EvalRunSummary[]> {
  const { data } = await client.get<EvalRunSummary[]>("/admin/eval/runs", {
    params: topicId ? { topic_id: topicId } : undefined,
  });
  return data;
}

export async function getEvalRun(runId: number): Promise<EvalRunDetail> {
  const { data } = await client.get<EvalRunDetail>(`/admin/eval/runs/${runId}`);
  return data;
}

export async function listEvalQuestions(topicId?: number): Promise<EvalQuestion[]> {
  const { data } = await client.get<EvalQuestion[]>("/admin/eval/questions", {
    params: topicId ? { topic_id: topicId } : undefined,
  });
  return data;
}

export async function triggerEvalRun(body: TriggerRunRequest): Promise<TriggerRunResponse> {
  const { data } = await client.post<TriggerRunResponse>("/admin/eval/runs", body);
  return data;
}
