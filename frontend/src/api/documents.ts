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

export interface UploadResult {
  task_id: number | null;
  status: string;
  message?: string | null;
}

export async function uploadDocumentPdf(
  topicId: number,
  file: File,
): Promise<UploadResult> {
  const fd = new FormData();
  fd.append("file", file);
  const { data } = await client.post<UploadResult>(
    `/topics/${topicId}/documents/upload`,
    fd,
    { headers: { "Content-Type": "multipart/form-data" } },
  );
  return data;
}

// --- Favorites (Wave-4) ---

export interface FavoriteState {
  document_id: number;
  favorite: boolean;
}

export interface FavoriteItem {
  document_id: number;
  source: string;
  title: string;
  authors: string[];
  published_at: string | null;
  url: string | null;
  abstract: string | null;
  favorited_at: string;
  last_opened_at: string | null;
  topic_ids: number[];
  abstract_only: boolean | null;
}

export interface FavoriteListResponse {
  items: FavoriteItem[];
  total: number;
}

export async function favoriteDocument(documentId: number) {
  const { data } = await client.put<FavoriteState>(`/documents/${documentId}/favorite`);
  return data;
}

export async function unfavoriteDocument(documentId: number) {
  const { data } = await client.delete<FavoriteState>(`/documents/${documentId}/favorite`);
  return data;
}

export async function listMyFavorites(limit = 50, offset = 0) {
  const { data } = await client.get<FavoriteListResponse>("/users/me/favorites", {
    params: { limit, offset },
  });
  return data;
}
