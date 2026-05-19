import { client } from "./client";

export interface CrossTopicCitation {
  topic_id: number | null;
  topic_name: string | null;
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

export interface CrossTopicQAResponse {
  answer: string;
  citations: CrossTopicCitation[];
  topics_searched: number[];
}

export async function crossTopicQA(body: {
  topic_ids: number[];
  question: string;
  mode?: string;
}): Promise<CrossTopicQAResponse> {
  const { data } = await client.post<CrossTopicQAResponse>(
    "/qa/cross-topic",
    body,
  );
  return data;
}
