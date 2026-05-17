import axios, { AxiosError, type AxiosInstance } from "axios";

import { useAuthStore } from "../stores/authStore";
import type { ApiError, TokenPair } from "../types/api";

const BASE_URL = "/api/v1";

export const client: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 60000,
});

client.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    config.headers = config.headers ?? {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

let refreshing: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  if (refreshing) return refreshing;
  refreshing = (async () => {
    const rt = useAuthStore.getState().refreshToken;
    if (!rt) return null;
    try {
      const resp = await axios.post<TokenPair>(`${BASE_URL}/auth/refresh`, {
        refresh_token: rt,
      });
      useAuthStore.getState().setAuth({
        accessToken: resp.data.access_token,
        refreshToken: resp.data.refresh_token,
        user: resp.data.user,
      });
      return resp.data.access_token;
    } catch {
      useAuthStore.getState().clear();
      return null;
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

client.interceptors.response.use(
  (resp) => resp,
  async (error: AxiosError<ApiError>) => {
    const original = error.config as (typeof error.config & { _retry?: boolean }) | undefined;
    if (
      error.response?.status === 401 &&
      original &&
      !original._retry &&
      !original.url?.includes("/auth/")
    ) {
      original._retry = true;
      const newToken = await refreshAccessToken();
      if (newToken) {
        original.headers = original.headers ?? {};
        original.headers.Authorization = `Bearer ${newToken}`;
        return client.request(original);
      }
    }
    return Promise.reject(error);
  }
);

export function apiErrorMessage(e: unknown): string {
  const err = e as AxiosError<ApiError>;
  return err.response?.data?.error?.message || err.message || "请求失败";
}
