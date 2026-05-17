import { client } from "./client";
import type {
  ReadingPathPublic,
  ResearchInsight,
  ResearchNote,
  TopicPulse,
} from "../types/api";

// --- Pulses ---
export async function getLatestPulse(topicId: number): Promise<TopicPulse | null> {
  const { data } = await client.get<TopicPulse | null>(`/topics/${topicId}/pulses/latest`);
  return data;
}

export async function listPulses(topicId: number) {
  const { data } = await client.get<TopicPulse[]>(`/topics/${topicId}/pulses`);
  return data;
}

export async function generatePulse(topicId: number) {
  const { data } = await client.post<{ status: string }>(`/topics/${topicId}/pulses/generate`);
  return data;
}

// --- Reading Paths ---
export async function getLatestReadingPath(topicId: number): Promise<ReadingPathPublic | null> {
  const { data } = await client.get<ReadingPathPublic | null>(
    `/topics/${topicId}/reading-paths/latest`
  );
  return data;
}

export async function generateReadingPath(topicId: number) {
  const { data } = await client.post<{ status: string }>(
    `/topics/${topicId}/reading-paths/generate`
  );
  return data;
}

// --- Insights ---
export async function listInsights(topicId: number, type?: string) {
  const { data } = await client.get<ResearchInsight[]>(`/topics/${topicId}/insights`, {
    params: type ? { type } : undefined,
  });
  return data;
}

export async function generateGaps(topicId: number) {
  const { data } = await client.post<{ status: string }>(
    `/topics/${topicId}/insights/gaps/generate`
  );
  return data;
}

// --- Notes ---
export async function listNotes(topicId: number) {
  const { data } = await client.get<ResearchNote[]>(`/topics/${topicId}/notes`);
  return data;
}

export async function createNote(
  topicId: number,
  body: { title?: string; content_md: string; tags?: string[]; pinned?: boolean }
) {
  const { data } = await client.post<ResearchNote>(`/topics/${topicId}/notes`, body);
  return data;
}

export async function updateNote(
  topicId: number,
  noteId: number,
  body: Partial<Pick<ResearchNote, "title" | "content_md" | "tags" | "pinned">>
) {
  const { data } = await client.patch<ResearchNote>(`/topics/${topicId}/notes/${noteId}`, body);
  return data;
}

export async function deleteNote(topicId: number, noteId: number) {
  await client.delete(`/topics/${topicId}/notes/${noteId}`);
}

export async function pinChatMessage(topicId: number, messageId: number) {
  const { data } = await client.post<ResearchNote>(
    `/topics/${topicId}/chat/messages/${messageId}/pin`
  );
  return data;
}
