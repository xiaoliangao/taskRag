import { client } from "./client";
import type { TokenPair, UserMe, UserPublic } from "../types/api";

export async function login(email: string, password: string) {
  const { data } = await client.post<TokenPair>("/auth/login", { email, password });
  return data;
}

export async function register(email: string, password: string) {
  const { data } = await client.post<UserPublic>("/auth/register", { email, password });
  return data;
}

export async function fetchMe() {
  const { data } = await client.get<UserMe>("/auth/me");
  return data;
}

export async function logout(refreshToken: string) {
  await client.post("/auth/logout", { refresh_token: refreshToken });
}
