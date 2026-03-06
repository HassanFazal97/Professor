import type {
  NotebookCreateBody,
  NotebookOut,
  PageCreateBody,
  PageOut,
  SessionStateOut,
  StrokeData,
  UserOut,
} from "@/types";
import { tokenStorage } from "./auth";

const BASE_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL?.replace(/\/+$/, "") ?? "http://localhost:8000";

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  auth = true,
): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (auth) {
    const token = tokenStorage.get();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }
  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${method} ${path} → ${res.status}: ${text}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ── Auth ──────────────────────────────────────────────────────────────────────

interface TokenResponse {
  access_token: string;
  token_type: string;
  user: UserOut;
}

export const auth = {
  register: (email: string, password: string, display_name?: string) =>
    request<TokenResponse>("POST", "/auth/register", { email, password, display_name }, false),

  login: (email: string, password: string) =>
    request<TokenResponse>("POST", "/auth/login", { email, password }, false),

  google: (id_token: string) =>
    request<TokenResponse>("POST", "/auth/google", { id_token }, false),

  me: () => request<UserOut>("GET", "/auth/me"),
};

// ── Notebooks ─────────────────────────────────────────────────────────────────

export const notebooks = {
  list: () => request<NotebookOut[]>("GET", "/notebooks"),

  create: (body: NotebookCreateBody) =>
    request<NotebookOut>("POST", "/notebooks", body),

  update: (id: string, body: Partial<NotebookCreateBody>) =>
    request<NotebookOut>("PATCH", `/notebooks/${id}`, body),

  delete: (id: string) => request<void>("DELETE", `/notebooks/${id}`),
};

// ── Pages ─────────────────────────────────────────────────────────────────────

export const pages = {
  list: (notebookId: string) =>
    request<PageOut[]>("GET", `/notebooks/${notebookId}/pages`),

  create: (notebookId: string, body: PageCreateBody) =>
    request<PageOut>("POST", `/notebooks/${notebookId}/pages`, body),

  get: (pageId: string) => request<PageOut>("GET", `/pages/${pageId}`),

  update: (pageId: string, body: Partial<PageCreateBody>) =>
    request<PageOut>("PATCH", `/pages/${pageId}`, body),

  delete: (pageId: string) => request<void>("DELETE", `/pages/${pageId}`),

  getSession: (pageId: string) =>
    request<SessionStateOut | null>("GET", `/pages/${pageId}/session`),

  saveSession: (
    pageId: string,
    body: { tldraw_snapshot?: Record<string, unknown> | null; overlay_strokes?: StrokeData[] },
  ) => request<SessionStateOut>("PUT", `/pages/${pageId}/session`, body),
};

export const api = { auth, notebooks, pages };
export default api;
