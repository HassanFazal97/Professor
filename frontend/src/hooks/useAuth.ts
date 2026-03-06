import { create } from "zustand";
import { api } from "@/lib/api";
import { tokenStorage, userStorage } from "@/lib/auth";
import type { UserOut } from "@/types";

interface AuthState {
  user: UserOut | null;
  token: string | null;
  isLoading: boolean;
  isAuthenticated: boolean;

  initialize: () => void;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, displayName?: string) => Promise<void>;
  googleLogin: (idToken: string) => Promise<void>;
  logout: () => void;
}

export const useAuth = create<AuthState>((set) => ({
  user: null,
  token: null,
  isLoading: false,
  isAuthenticated: false,

  initialize: () => {
    const token = tokenStorage.get();
    const user = userStorage.get();
    if (token && user) {
      set({ token, user, isAuthenticated: true });
    }
  },

  login: async (email, password) => {
    set({ isLoading: true });
    try {
      const res = await api.auth.login(email, password);
      tokenStorage.set(res.access_token);
      userStorage.set(res.user);
      set({ token: res.access_token, user: res.user, isAuthenticated: true });
    } finally {
      set({ isLoading: false });
    }
  },

  register: async (email, password, displayName) => {
    set({ isLoading: true });
    try {
      const res = await api.auth.register(email, password, displayName);
      tokenStorage.set(res.access_token);
      userStorage.set(res.user);
      set({ token: res.access_token, user: res.user, isAuthenticated: true });
    } finally {
      set({ isLoading: false });
    }
  },

  googleLogin: async (idToken) => {
    set({ isLoading: true });
    try {
      const res = await api.auth.google(idToken);
      tokenStorage.set(res.access_token);
      userStorage.set(res.user);
      set({ token: res.access_token, user: res.user, isAuthenticated: true });
    } finally {
      set({ isLoading: false });
    }
  },

  logout: () => {
    tokenStorage.clear();
    userStorage.clear();
    set({ user: null, token: null, isAuthenticated: false });
  },
}));
