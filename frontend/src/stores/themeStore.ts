import { create } from "zustand";
import { persist } from "zustand/middleware";

export type ThemeMode = "night" | "day";

interface ThemeState {
  mode: ThemeMode;
  setMode: (m: ThemeMode) => void;
  toggle: () => void;
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set, get) => ({
      mode: "night",
      setMode: (m) => set({ mode: m }),
      toggle: () => set({ mode: get().mode === "night" ? "day" : "night" }),
    }),
    { name: "taskrag.theme" }
  )
);

// Reflect mode onto <html data-theme="..."> so CSS can branch via attribute selectors.
// Called from a tiny subscriber in main.tsx — keeps the store agnostic of the DOM.
export function applyThemeAttribute(mode: ThemeMode) {
  const root = document.documentElement;
  root.setAttribute("data-theme", mode);
}
