import { client } from "./client";

export interface TranslateResponse {
  text: string;
  source_lang: string;
  target_lang: string;
  cached: boolean;
}

export async function translateText(text: string, target_lang?: string) {
  const { data } = await client.post<TranslateResponse>("/translate", {
    text,
    target_lang,
  });
  return data;
}

export async function translateStatus(): Promise<{ enabled: boolean }> {
  const { data } = await client.get<{ enabled: boolean }>("/translate/status");
  return data;
}
