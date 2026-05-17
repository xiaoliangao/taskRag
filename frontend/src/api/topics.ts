import { client } from "./client";
import type { Topic } from "../types/api";

export interface TopicCreateBody {
  name: string;
  description?: string;
  keywords: string[];
  sources: string[];
  schedule_type?: "daily" | "weekly";
  schedule_time?: string;
  max_results_per_source_per_run?: number;
  enabled?: boolean;
}

export interface TopicUpdateBody extends Partial<TopicCreateBody> {}

export async function listTopics() {
  const { data } = await client.get<Topic[]>("/topics");
  return data;
}

export async function getTopic(id: number) {
  const { data } = await client.get<Topic>(`/topics/${id}`);
  return data;
}

export async function createTopic(body: TopicCreateBody) {
  const { data } = await client.post<Topic>("/topics", body);
  return data;
}

export async function updateTopic(id: number, body: TopicUpdateBody) {
  const { data } = await client.patch<Topic>(`/topics/${id}`, body);
  return data;
}

export async function deleteTopic(id: number) {
  await client.delete(`/topics/${id}`);
}

export async function manualCollect(id: number) {
  const { data } = await client.post<{ tasks: { id: number; source: string; status: string }[] }>(
    `/topics/${id}/collect`
  );
  return data;
}

export interface PreviewItem {
  source: string;
  external_id: string;
  title: string;
  authors: string[];
  published_at: string | null;
  url: string;
  abstract: string | null;
  raw_content_url?: string | null;
  matched_keyword?: string | null;
  metadata?: Record<string, unknown>;
  already_in_topic: boolean;
}

export interface PreviewResponse {
  sources_queried: string[];
  rate_limited_sources: string[];
  items: PreviewItem[];
}

export async function searchPreview(
  topicId: number,
  body: { sources?: string[]; limit?: number } = {}
) {
  const { data } = await client.post<PreviewResponse>(
    `/topics/${topicId}/search-preview`,
    body
  );
  return data;
}

export async function collectSelected(topicId: number, picks: PreviewItem[]) {
  const { data } = await client.post<{
    task_id: number;
    count: number;
    status: string;
  }>(`/topics/${topicId}/collect-selected`, { picks });
  return data;
}
