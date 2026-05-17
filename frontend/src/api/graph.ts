import { client } from "./client";
import type { GraphResponse } from "../types/api";

export async function getGraph(
  topicId: number,
  params: { relation_types?: string; limit_nodes?: number } = {},
): Promise<GraphResponse> {
  const { data } = await client.get<GraphResponse>(`/topics/${topicId}/graph`, { params });
  return data;
}

export async function rebuildGraph(
  topicId: number,
): Promise<{ status: string; edges: number; nodes: number }> {
  const { data } = await client.post(`/topics/${topicId}/graph/rebuild`);
  return data;
}
