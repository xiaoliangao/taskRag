import { client } from "./client";

export interface MethodEntity {
  id: number;
  name: string;
  normalized_name: string;
  description: string | null;
  first_seen_document_id: number | null;
  first_seen_at: string | null;
  document_count: number;
}

export interface MethodEdge {
  id: number;
  from_method_id: number;
  to_method_id: number;
  relation_type: string;
  confidence: number;
  explanation: string | null;
}

export interface MethodTimelineResponse {
  methods: MethodEntity[];
  edges: MethodEdge[];
}

export async function getMethodTimeline(
  topicId: number,
): Promise<MethodTimelineResponse> {
  const { data } = await client.get<MethodTimelineResponse>(
    `/topics/${topicId}/methods/timeline`,
  );
  return data;
}

export async function rebuildMethodTimeline(
  topicId: number,
  extractEdges = true,
): Promise<{ status: string; task_id?: string }> {
  const { data } = await client.post(
    `/topics/${topicId}/methods/timeline/rebuild`,
    null,
    { params: { extract_edges: extractEdges } },
  );
  return data;
}
