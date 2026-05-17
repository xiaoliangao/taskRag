import { client } from "./client";
import type { SettingsPublic } from "../types/api";

export async function getSettings() {
  const { data } = await client.get<SettingsPublic>("/settings");
  return data;
}

export async function patchSettings(body: Partial<SettingsPublic>) {
  const { data } = await client.patch<SettingsPublic>("/settings", body);
  return data;
}
