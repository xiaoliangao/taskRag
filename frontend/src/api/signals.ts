import { client } from "./client";
import type {
  DocumentSignalPublic,
  SignalRefreshResponse,
} from "../types/api";

export async function listSignals(
  topicId: number,
  params: { signal_type?: string; limit?: number } = {},
): Promise<DocumentSignalPublic[]> {
  const { data } = await client.get<DocumentSignalPublic[]>(
    `/topics/${topicId}/signals`,
    { params },
  );
  return data;
}

export async function refreshSignals(
  topicId: number,
): Promise<SignalRefreshResponse> {
  const { data } = await client.post<SignalRefreshResponse>(
    `/topics/${topicId}/signals/refresh`,
    null,
  );
  return data;
}
