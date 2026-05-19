import { client } from "./client";

export interface AgentStep {
  role: "thought" | "tool_call" | "observation" | "final" | string;
  content: string;
  tool: string | null;
  args: Record<string, unknown> | null;
}

export interface AgentResponse {
  final_answer: string;
  steps: AgentStep[];
  error: string | null;
  topics_searched: number[];
}

export async function runAgent(body: {
  question: string;
  topic_ids?: number[];
  max_steps?: number;
}): Promise<AgentResponse> {
  const { data } = await client.post<AgentResponse>("/qa/agent", body);
  return data;
}
