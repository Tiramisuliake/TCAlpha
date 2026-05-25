import { create } from "zustand";

interface AuthState {
  userId: number;
  token: string | null;
  setToken: (t: string | null) => void;
}

export const useAuth = create<AuthState>((set) => ({
  userId: 1, // Phase 0 占位
  token: null,
  setToken: (t) => set({ token: t }),
}));
