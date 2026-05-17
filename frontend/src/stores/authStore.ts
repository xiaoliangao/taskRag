import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { UserPublic } from "../types/api";

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: UserPublic | null;
  setAuth: (a: { accessToken: string; refreshToken: string; user: UserPublic }) => void;
  setAccessToken: (token: string) => void;
  clear: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      setAuth: ({ accessToken, refreshToken, user }) =>
        set({ accessToken, refreshToken, user }),
      setAccessToken: (token) => set({ accessToken: token }),
      clear: () => set({ accessToken: null, refreshToken: null, user: null }),
    }),
    { name: "taskrag-auth" }
  )
);
