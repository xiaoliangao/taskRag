import { client } from "./client";
import type { DocumentDetail, DocumentListResponse } from "../types/api";

export async function listDocuments(
  topicId: number,
  params: { source?: string; q?: string; from?: string; to?: string; page?: number; page_size?: number } = {}
) {
  const { data } = await client.get<DocumentListResponse>(`/topics/${topicId}/documents`, { params });
  return data;
}

export async function getDocument(topicId: number, documentId: number) {
  const { data } = await client.get<DocumentDetail>(`/topics/${topicId}/documents/${documentId}`);
  return data;
}

export async function getDocumentPdfBlobUrl(topicId: number, documentId: number): Promise<string> {
  const resp = await client.get(`/topics/${topicId}/documents/${documentId}/pdf`, {
    responseType: "blob",
  });
  const blob = new Blob([resp.data], { type: "application/pdf" });
  return URL.createObjectURL(blob);
}
