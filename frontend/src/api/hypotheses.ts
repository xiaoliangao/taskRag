import { client } from "./client";
import type {
  HypothesisCheckPublic,
  HypothesisCheckSummary,
} from "../types/api";

export async function runHypothesis(
  topicId: number,
  hypothesis: string,
): Promise<HypothesisCheckPublic> {
  const { data } = await client.post<HypothesisCheckPublic>(
    `/topics/${topicId}/hypotheses/check`,
    { hypothesis },
  );
  return data;
}

export async function listHypotheses(
  topicId: number,
  limit = 20,
): Promise<HypothesisCheckSummary[]> {
  const { data } = await client.get<HypothesisCheckSummary[]>(
    `/topics/${topicId}/hypotheses`,
    { params: { limit } },
  );
  return data;
}

export async function getHypothesis(
  topicId: number,
  checkId: number,
): Promise<HypothesisCheckPublic> {
  const { data } = await client.get<HypothesisCheckPublic>(
    `/topics/${topicId}/hypotheses/${checkId}`,
  );
  return data;
}

export async function deleteHypothesis(
  topicId: number,
  checkId: number,
): Promise<{ deleted: boolean; id: number }> {
  const { data } = await client.delete(
    `/topics/${topicId}/hypotheses/${checkId}`,
  );
  return data;
}
