import { client } from "./client";
import type { ExportPayload } from "../types/api";

export async function exportBibtex(topicId: number): Promise<ExportPayload> {
  const { data } = await client.post<ExportPayload>(`/topics/${topicId}/exports/bibtex`);
  return data;
}

export async function exportMarkdown(topicId: number): Promise<ExportPayload> {
  const { data } = await client.post<ExportPayload>(`/topics/${topicId}/exports/markdown`);
  return data;
}
