import { client } from "./client";

export interface CitationNode {
  id: number;
  title: string | null;
  year: number | null;
  source: string | null;
  cited_by_count: number | null;
  recent_citations: number;
  in_degree: number;
  out_degree: number;
}

export interface CitationEdge {
  source: number; // citing document id
  target: number; // cited document id
}

export interface CitationGraph {
  nodes: CitationNode[];
  edges: CitationEdge[];
  stats: { total: number; enriched: number; edges: number };
}

export interface CitationRebuildResult {
  status: string;
  enriched: number;
  remaining: number;
  edges: number;
  nodes: number;
}

export async function getCitationGraph(topicId: number): Promise<CitationGraph> {
  const { data } = await client.get<CitationGraph>(`/topics/${topicId}/citation-graph`);
  return data;
}

export async function rebuildCitationGraph(topicId: number): Promise<CitationRebuildResult> {
  const { data } = await client.post<CitationRebuildResult>(
    `/topics/${topicId}/citation-graph/rebuild`,
  );
  return data;
}
