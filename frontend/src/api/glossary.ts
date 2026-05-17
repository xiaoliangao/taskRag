import { client } from "./client";
import type { GlossaryTermPublic } from "../types/api";

export async function listGlossary(
  topicId: number,
  limit = 80,
): Promise<GlossaryTermPublic[]> {
  const { data } = await client.get<GlossaryTermPublic[]>(
    `/topics/${topicId}/glossary`,
    { params: { limit } },
  );
  return data;
}

export async function generateGlossary(
  topicId: number,
  limitTerms = 15,
): Promise<{ status: string; generated: number; skipped: number }> {
  const { data } = await client.post(`/topics/${topicId}/glossary/generate`, null, {
    params: { limit_terms: limitTerms },
  });
  return data;
}
