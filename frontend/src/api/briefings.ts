import { client } from "./client";
import type { DocumentBriefingResponse, UserDocStatePublic } from "../types/api";

export async function getBriefing(topicId: number, documentId: number) {
  const { data } = await client.get<DocumentBriefingResponse>(
    `/topics/${topicId}/documents/${documentId}/briefing`
  );
  return data;
}

export async function generateBriefing(topicId: number, documentId: number) {
  const { data } = await client.post<{ document_id: number; status: string; message?: string }>(
    `/topics/${topicId}/documents/${documentId}/briefing/generate`
  );
  return data;
}

export async function patchDocState(
  topicId: number,
  documentId: number,
  body: Partial<UserDocStatePublic>
) {
  const { data } = await client.patch<UserDocStatePublic>(
    `/topics/${topicId}/documents/${documentId}/state`,
    body
  );
  return data;
}
