import { client } from "./client";
import type {
  ComparisonSessionPublic,
  ComparisonSessionSummary,
} from "../types/api";

export async function createComparison(
  topicId: number,
  title: string,
  documentIds: number[],
): Promise<ComparisonSessionPublic> {
  const { data } = await client.post<ComparisonSessionPublic>(
    `/topics/${topicId}/comparisons`,
    { title, document_ids: documentIds },
  );
  return data;
}

export async function listComparisons(
  topicId: number,
): Promise<ComparisonSessionSummary[]> {
  const { data } = await client.get<ComparisonSessionSummary[]>(
    `/topics/${topicId}/comparisons`,
  );
  return data;
}

export async function getComparison(
  topicId: number,
  id: number,
): Promise<ComparisonSessionPublic> {
  const { data } = await client.get<ComparisonSessionPublic>(
    `/topics/${topicId}/comparisons/${id}`,
  );
  return data;
}

export async function generateComparison(
  topicId: number,
  id: number,
): Promise<ComparisonSessionPublic> {
  const { data } = await client.post<ComparisonSessionPublic>(
    `/topics/${topicId}/comparisons/${id}/generate`,
  );
  return data;
}

export async function exportComparison(
  topicId: number,
  id: number,
  format: "markdown" | "latex" = "markdown",
): Promise<{ format: string; content: string }> {
  const { data } = await client.get(
    `/topics/${topicId}/comparisons/${id}/export`,
    { params: { format } },
  );
  return data;
}
