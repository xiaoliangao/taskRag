import { client } from "./client";
import type {
  TermDocumentRef,
  TopicTermPublic,
  TrendGenerateResponse,
  TrendRunPublic,
  TrendRunSummary,
} from "../types/api";

export async function getLatestTrend(
  topicId: number,
  windowDays = 60,
): Promise<TrendRunPublic | null> {
  const { data } = await client.get<TrendRunPublic | null>(
    `/topics/${topicId}/trends/latest`,
    { params: { window_days: windowDays } },
  );
  return data;
}

export async function listTrendRuns(topicId: number): Promise<TrendRunSummary[]> {
  const { data } = await client.get<TrendRunSummary[]>(
    `/topics/${topicId}/trends/runs`,
  );
  return data;
}

export async function getTrendRun(
  topicId: number,
  runId: number,
): Promise<TrendRunPublic> {
  const { data } = await client.get<TrendRunPublic>(
    `/topics/${topicId}/trends/runs/${runId}`,
  );
  return data;
}

export async function generateTrend(
  topicId: number,
  windowDays = 60,
): Promise<TrendGenerateResponse> {
  const { data } = await client.post<TrendGenerateResponse>(
    `/topics/${topicId}/trends/generate`,
    null,
    { params: { window_days: windowDays } },
  );
  return data;
}

export async function listTopicTerms(
  topicId: number,
  params: { term_type?: string; limit?: number } = {},
): Promise<TopicTermPublic[]> {
  const { data } = await client.get<TopicTermPublic[]>(
    `/topics/${topicId}/terms`,
    { params },
  );
  return data;
}

export async function listDocumentsForTerm(
  topicId: number,
  termId: number,
): Promise<TermDocumentRef[]> {
  const { data } = await client.get<TermDocumentRef[]>(
    `/topics/${topicId}/terms/${termId}/documents`,
  );
  return data;
}
