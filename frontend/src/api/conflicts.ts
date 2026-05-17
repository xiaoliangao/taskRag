import { client } from "./client";
import type {
  ConflictDetectResponse,
  ConflictRelationPublic,
  PaperClaimPublic,
} from "../types/api";

export async function listClaims(
  topicId: number,
  params: { document_id?: number; claim_type?: string; limit?: number } = {},
): Promise<PaperClaimPublic[]> {
  const { data } = await client.get<PaperClaimPublic[]>(
    `/topics/${topicId}/claims`,
    { params },
  );
  return data;
}

export async function extractClaims(
  topicId: number,
  limitDocs = 30,
): Promise<ConflictDetectResponse> {
  const { data } = await client.post<ConflictDetectResponse>(
    `/topics/${topicId}/claims/extract`,
    null,
    { params: { limit_docs: limitDocs } },
  );
  return data;
}

export async function detectConflicts(
  topicId: number,
  extractFirst = true,
): Promise<ConflictDetectResponse> {
  const { data } = await client.post<ConflictDetectResponse>(
    `/topics/${topicId}/conflicts/detect`,
    null,
    { params: { extract_first: extractFirst } },
  );
  return data;
}

export async function listConflicts(
  topicId: number,
  params: { relation_type?: string; min_confidence?: number; limit?: number } = {},
): Promise<ConflictRelationPublic[]> {
  const { data } = await client.get<ConflictRelationPublic[]>(
    `/topics/${topicId}/conflicts`,
    { params },
  );
  return data;
}

export async function sendConflictFeedback(
  topicId: number,
  relationId: number,
  feedback: "useful" | "dismissed" | "confirmed",
): Promise<{ id: number; reviewed_by_user: boolean; user_feedback: string }> {
  const { data } = await client.patch(
    `/topics/${topicId}/conflicts/${relationId}/feedback`,
    { feedback },
  );
  return data;
}
