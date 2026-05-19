import { client } from "./client";

export interface AdminUserRow {
  id: number;
  email: string;
  created_at: string;
  is_admin: boolean;
  disabled_at: string | null;
  topic_count: number;
  document_count: number;
}

export interface AdminUserList {
  items: AdminUserRow[];
  total: number;
  page: number;
  page_size: number;
}

export interface AdminUserPatch {
  is_admin?: boolean;
  disabled?: boolean;
}

export interface AdminResetPasswordResponse {
  delivery: "email" | "log";
  new_password_preview: string | null;
}

export interface AdminBroadcastRequest {
  subject: string;
  body: string;
  target: "all" | "selected";
  user_ids?: number[];
}

export interface AdminBroadcastResponse {
  queued: number;
  skipped: number;
  delivery: "email" | "log";
}

export interface AdminHealthComponent {
  name: string;
  status: "ok" | "warn" | "fail" | "skipped";
  detail: string | null;
  latency_ms: number | null;
}

export interface AdminHealthReport {
  checked_at: string;
  components: AdminHealthComponent[];
}

export async function listAdminUsers(params: { q?: string; page?: number; page_size?: number }) {
  const { data } = await client.get<AdminUserList>("/admin/users", { params });
  return data;
}

export async function getAdminUser(id: number) {
  const { data } = await client.get<AdminUserRow>(`/admin/users/${id}`);
  return data;
}

export async function patchAdminUser(id: number, body: AdminUserPatch) {
  const { data } = await client.patch<AdminUserRow>(`/admin/users/${id}`, body);
  return data;
}

export async function deleteAdminUser(id: number) {
  await client.delete(`/admin/users/${id}`);
}

export async function resetUserPassword(id: number) {
  const { data } = await client.post<AdminResetPasswordResponse>(
    `/admin/users/${id}/reset-password`
  );
  return data;
}

export async function adminBroadcast(body: AdminBroadcastRequest) {
  const { data } = await client.post<AdminBroadcastResponse>("/admin/broadcast", body);
  return data;
}

export async function adminHealth() {
  const { data } = await client.get<AdminHealthReport>("/admin/health");
  return data;
}
