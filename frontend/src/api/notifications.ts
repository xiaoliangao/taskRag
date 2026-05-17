import { client } from "./client";
import type { NotificationItem, NotificationListResponse } from "../types/api";

export async function listNotifications(params: { unread_only?: boolean; page?: number; page_size?: number } = {}) {
  const { data } = await client.get<NotificationListResponse>("/notifications", { params });
  return data;
}

export async function markRead(id: number) {
  const { data } = await client.patch<NotificationItem>(`/notifications/${id}/read`);
  return data;
}

export async function markAllRead() {
  const { data } = await client.patch<{ updated_count: number }>(`/notifications/read-all`);
  return data;
}
