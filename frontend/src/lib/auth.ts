import type { UserOut } from "@/types";

const TOKEN_KEY = "professor_token";
const USER_KEY = "professor_user";

function setCookie(name: string, value: string, days: number) {
  if (typeof document === "undefined") return;
  const expires = new Date(Date.now() + days * 864e5).toUTCString();
  document.cookie = `${name}=${encodeURIComponent(value)}; expires=${expires}; path=/; SameSite=Lax`;
}

function clearCookie(name: string) {
  if (typeof document === "undefined") return;
  document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/; SameSite=Lax`;
}

export const tokenStorage = {
  get(): string | null {
    if (typeof localStorage === "undefined") return null;
    return localStorage.getItem(TOKEN_KEY);
  },
  set(token: string) {
    localStorage.setItem(TOKEN_KEY, token);
    setCookie(TOKEN_KEY, token, 7);
  },
  clear() {
    localStorage.removeItem(TOKEN_KEY);
    clearCookie(TOKEN_KEY);
  },
};

export const userStorage = {
  get(): UserOut | null {
    if (typeof localStorage === "undefined") return null;
    const raw = localStorage.getItem(USER_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw) as UserOut;
    } catch {
      return null;
    }
  },
  set(user: UserOut) {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  },
  clear() {
    localStorage.removeItem(USER_KEY);
  },
};
