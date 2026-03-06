import { create } from "zustand";
import { api } from "@/lib/api";
import type { NotebookCreateBody, NotebookOut, PageCreateBody, PageOut, PaperStyle } from "@/types";

interface NotebooksState {
  notebooks: NotebookOut[];
  pages: PageOut[];
  isLoading: boolean;
  error: string | null;

  fetchNotebooks: () => Promise<void>;
  createNotebook: (body: NotebookCreateBody) => Promise<NotebookOut>;
  deleteNotebook: (id: string) => Promise<void>;

  fetchPages: (notebookId: string) => Promise<void>;
  createPage: (notebookId: string, body: PageCreateBody) => Promise<PageOut>;
  deletePage: (pageId: string) => Promise<void>;
}

export const useNotebooks = create<NotebooksState>((set, get) => ({
  notebooks: [],
  pages: [],
  isLoading: false,
  error: null,

  fetchNotebooks: async () => {
    set({ isLoading: true, error: null });
    try {
      const nbs = await api.notebooks.list();
      set({ notebooks: nbs });
    } catch (e) {
      set({ error: String(e) });
    } finally {
      set({ isLoading: false });
    }
  },

  createNotebook: async (body) => {
    const nb = await api.notebooks.create(body);
    set((s) => ({ notebooks: [nb, ...s.notebooks] }));
    return nb;
  },

  deleteNotebook: async (id) => {
    await api.notebooks.delete(id);
    set((s) => ({ notebooks: s.notebooks.filter((n) => n.id !== id) }));
  },

  fetchPages: async (notebookId) => {
    set({ isLoading: true, error: null });
    try {
      const ps = await api.pages.list(notebookId);
      set({ pages: ps });
    } catch (e) {
      set({ error: String(e) });
    } finally {
      set({ isLoading: false });
    }
  },

  createPage: async (notebookId, body) => {
    const page = await api.pages.create(notebookId, body);
    set((s) => ({ pages: [...s.pages, page] }));
    return page;
  },

  deletePage: async (pageId) => {
    await api.pages.delete(pageId);
    set((s) => ({ pages: s.pages.filter((p) => p.id !== pageId) }));
  },
}));
