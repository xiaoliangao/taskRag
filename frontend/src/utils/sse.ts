import { fetchEventSource } from "@microsoft/fetch-event-source";

import { useAuthStore } from "../stores/authStore";

export interface SseHandlers {
  onToken?: (text: string) => void;
  onCitations?: (items: any[]) => void;
  onDone?: (messageId?: number) => void;
  onError?: (msg: string) => void;
}

export async function consumeStream(url: string, handlers: SseHandlers, signal?: AbortSignal) {
  const token = useAuthStore.getState().accessToken;
  await fetchEventSource(url, {
    method: "GET",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    signal,
    openWhenHidden: true,
    onmessage(ev) {
      try {
        const payload = ev.data ? JSON.parse(ev.data) : {};
        switch (ev.event) {
          case "token":
            handlers.onToken?.(payload.text ?? "");
            break;
          case "citations":
            handlers.onCitations?.(payload.items ?? []);
            break;
          case "done":
            handlers.onDone?.(payload.message_id);
            break;
          case "error":
            handlers.onError?.(payload.message || payload.code || "stream error");
            break;
        }
      } catch (err) {
        handlers.onError?.(String(err));
      }
    },
    onerror(err) {
      handlers.onError?.(String(err));
      throw err; // stop reconnection
    },
  });
}
