import { client } from "./client";
import type {
  WritingProjectPublic,
  WritingProjectSummary,
} from "../types/api";

export async function createWritingProject(
  topicId: number,
  body: { title: string; user_intent: string; document_ids: number[] },
): Promise<WritingProjectPublic> {
  const { data } = await client.post<WritingProjectPublic>(
    `/topics/${topicId}/writing-projects`,
    body,
  );
  return data;
}

export async function listWritingProjects(
  topicId: number,
): Promise<WritingProjectSummary[]> {
  const { data } = await client.get<WritingProjectSummary[]>(
    `/topics/${topicId}/writing-projects`,
  );
  return data;
}

export async function getWritingProject(
  topicId: number,
  id: number,
): Promise<WritingProjectPublic> {
  const { data } = await client.get<WritingProjectPublic>(
    `/topics/${topicId}/writing-projects/${id}`,
  );
  return data;
}

export async function generateOutline(
  topicId: number,
  id: number,
): Promise<WritingProjectPublic> {
  const { data } = await client.post<WritingProjectPublic>(
    `/topics/${topicId}/writing-projects/${id}/generate-outline`,
  );
  return data;
}

export async function generateDraft(
  topicId: number,
  id: number,
): Promise<WritingProjectPublic> {
  const { data } = await client.post<WritingProjectPublic>(
    `/topics/${topicId}/writing-projects/${id}/generate-draft`,
  );
  return data;
}
