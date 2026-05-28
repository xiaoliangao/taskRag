import { client } from "./client";

export interface RecommendedItem {
  // Always present
  source: string;
  external_id: string;
  title: string;
  authors: string[];
  published_at: string | null;
  url: string | null;
  abstract: string | null;
  score: number | null;
  rationale: string | null;
  // Provenance
  in_corpus: boolean;
  document_id: number | null;  // populated when in_corpus
  topic_ids: number[];          // topics this in-corpus doc belongs to
}

export interface RecommendationResponse {
  items: RecommendedItem[];
  favorites_count: number;
  generated_at: string;
  cached: boolean;
}

export async function getMyRecommendations(limit = 10, refresh = false) {
  const { data } = await client.get<RecommendationResponse>(
    "/users/me/recommendations",
    { params: { limit, refresh } },
  );
  return data;
}
