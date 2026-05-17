import { client } from "./client";
import type { TaskItem, TaskListResponse } from "../types/api";

export async function listTasks(topicId: number, limit = 50) {
  const { data } = await client.get<TaskListResponse>(`/topics/${topicId}/tasks`, {
    params: { limit },
  });
  return data;
}

export async function retryTask(taskId: number) {
  const { data } = await client.post<TaskItem>(`/tasks/${taskId}/retry`);
  return data;
}
