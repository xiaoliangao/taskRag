import { client } from "./client";
import type { ChatMessage, ChatMode, ChatSession, Citation } from "../types/api";

export async function listSessions(topicId: number) {
  const { data } = await client.get<ChatSession[]>(`/topics/${topicId}/chat/sessions`);
  return data;
}

export async function createSession(
  topicId: number,
  title: string,
  mode: ChatMode = "default",
) {
  const { data } = await client.post<ChatSession>(`/topics/${topicId}/chat/sessions`, {
    title,
    mode,
  });
  return data;
}

export async function updateSession(
  topicId: number,
  sessionId: number,
  body: { title?: string; mode?: ChatMode },
) {
  const { data } = await client.patch<ChatSession>(
    `/topics/${topicId}/chat/sessions/${sessionId}`,
    body,
  );
  return data;
}

export async function listMessages(topicId: number, sessionId: number) {
  const { data } = await client.get<ChatMessage[]>(
    `/topics/${topicId}/chat/sessions/${sessionId}/messages`
  );
  return data;
}

export interface PostMessageResponse {
  message_id: number;
  role: string;
  content: string;
  citations: Citation[];
}

export async function postMessage(topicId: number, sessionId: number, content: string) {
  const { data } = await client.post<PostMessageResponse>(
    `/topics/${topicId}/chat/sessions/${sessionId}/messages`,
    { content, stream: false }
  );
  return data;
}

export function streamUrl(topicId: number, sessionId: number, message: string) {
  const qs = new URLSearchParams({ message });
  return `/api/v1/topics/${topicId}/chat/sessions/${sessionId}/stream?${qs.toString()}`;
}

// --- v1.5 Conversation Memory ---

export interface ChatMemorySummary {
  id: number;
  chat_session_id: number;
  summary_md: string;
  memory_items: Array<{
    memory_type?: string;
    content?: string;
    confidence?: number;
  }>;
  message_count_at_gen: number;
  generated_at: string;
}

export async function listChatMemory(
  topicId: number,
  limit = 20,
): Promise<ChatMemorySummary[]> {
  const { data } = await client.get<ChatMemorySummary[]>(
    `/topics/${topicId}/chat/memory`,
    { params: { limit } },
  );
  return data;
}

export async function deleteChatMemory(
  topicId: number,
  summaryId: number,
): Promise<{ deleted: boolean; id: number }> {
  const { data } = await client.delete(
    `/topics/${topicId}/chat/memory/${summaryId}`,
  );
  return data;
}
