import { create } from "zustand";
import { api } from "@/lib/api";

interface AuthState {
  token: string | null;
  user: { id: string; email: string; name: string } | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, name: string, password: string) => Promise<void>;
  logout: () => void;
  loadFromStorage: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  user: null,
  isLoading: true,

  login: async (email, password) => {
    const { access_token } = await api.login(email, password);
    api.setToken(access_token);
    localStorage.setItem("token", access_token);
    const user = await api.getMe();
    set({ token: access_token, user, isLoading: false });
  },

  register: async (email, name, password) => {
    await api.register(email, name, password);
    // Auto-login after registration
    const { access_token } = await api.login(email, password);
    api.setToken(access_token);
    localStorage.setItem("token", access_token);
    const user = await api.getMe();
    set({ token: access_token, user, isLoading: false });
  },

  logout: () => {
    api.setToken(null);
    localStorage.removeItem("token");
    set({ token: null, user: null, isLoading: false });
  },

  loadFromStorage: async () => {
    const token = localStorage.getItem("token");
    if (token) {
      api.setToken(token);
      try {
        const user = await api.getMe();
        set({ token, user, isLoading: false });
      } catch {
        localStorage.removeItem("token");
        api.setToken(null);
        set({ token: null, user: null, isLoading: false });
      }
    } else {
      set({ isLoading: false });
    }
  },
}));
