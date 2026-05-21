import { client } from "./client";
import type { PreviewItem } from "./topics";

export interface DiscoverSearchRequest {
  query: string;
  sources?: string[];
  limit?: number;
  days?: number;
}

export interface DiscoverSearchResponse {
  items: PreviewItem[];
  rate_limited_sources: string[];
  sources_queried: string[];
}

export interface DiscoverIngestRequest {
  picks: PreviewItem[];
  topic_id?: number;
  new_topic_name?: string;
}

export interface DiscoverIngestResponse {
  topic_id: number;
  topic_name: string;
  task_id: number;
  count: number;
  status: string;
  created_topic: boolean;
}

export async function discoverSearch(body: DiscoverSearchRequest) {
  const { data } = await client.post<DiscoverSearchResponse>("/discover/search", body);
  return data;
}

export async function discoverIngest(body: DiscoverIngestRequest) {
  const { data } = await client.post<DiscoverIngestResponse>("/discover/ingest", body);
  return data;
}
