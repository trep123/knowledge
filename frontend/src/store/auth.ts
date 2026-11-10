import { create } from "zustand";

interface AuthState {
  token: string | null;
  username: string;
  role: string;
  login: (token: string, username: string, role: string) => void;
  logout: () => void;
}

export const useAuth = create<AuthState>((set) => ({
  token: localStorage.getItem("kb_token"),
  username: localStorage.getItem("kb_username") || "",
  role: localStorage.getItem("kb_role") || "",
  login: (token, username, role) => {
    localStorage.setItem("kb_token", token);
    localStorage.setItem("kb_username", username);
    localStorage.setItem("kb_role", role);
    set({ token, username, role });
  },
  logout: () => {
    localStorage.removeItem("kb_token");
    localStorage.removeItem("kb_username");
    localStorage.removeItem("kb_role");
    set({ token: null, username: "", role: "" });
  },
}));
