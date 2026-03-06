"use client";

import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { useNotebooks } from "@/hooks/useNotebooks";
import PageCard from "@/components/PageCard";
import type { PageCreateBody, PaperStyle } from "@/types";

const PAPER_OPTIONS: { value: PaperStyle; label: string; description: string }[] = [
  { value: "blank", label: "Blank", description: "Clean white canvas" },
  { value: "lined", label: "Lined", description: "Horizontal ruled lines" },
  { value: "graph", label: "Graph", description: "Grid pattern" },
];

export default function NotebookPage() {
  const params = useParams();
  const notebookId = params.id as string;
  const router = useRouter();
  const { notebooks, pages, fetchNotebooks, fetchPages, createPage, deletePage } = useNotebooks();

  const [showNewPage, setShowNewPage] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newStyle, setNewStyle] = useState<PaperStyle>("blank");
  const [saving, setSaving] = useState(false);

  const notebook = notebooks.find((n) => n.id === notebookId);

  useEffect(() => {
    if (notebooks.length === 0) fetchNotebooks();
    fetchPages(notebookId);
  }, [notebookId, fetchNotebooks, fetchPages, notebooks.length]);

  const handleCreatePage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    setSaving(true);
    try {
      const page = await createPage(notebookId, {
        title: newTitle.trim(),
        paper_style: newStyle,
      } satisfies PageCreateBody);
      setShowNewPage(false);
      setNewTitle("");
      router.push(`/notebook/${notebookId}/${page.id}`);
    } finally {
      setSaving(false);
    }
  };

  const handleDeletePage = async (pageId: string) => {
    if (!confirm("Delete this page and its session?")) return;
    await deletePage(pageId);
  };

  return (
    <div className="flex h-full flex-col bg-gray-50">
      {/* Breadcrumb nav */}
      <header className="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-3 shadow-sm">
        <div className="flex items-center gap-2 text-sm">
          <button
            onClick={() => router.push("/library")}
            className="text-indigo-600 hover:underline"
          >
            Library
          </button>
          <span className="text-gray-400">/</span>
          <span className="font-medium text-gray-900">
            {notebook ? `${notebook.emoji} ${notebook.title}` : "Notebook"}
          </span>
        </div>
        <button
          onClick={() => setShowNewPage(true)}
          className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
        >
          + New Page
        </button>
      </header>

      <main className="flex-1 overflow-auto px-6 py-8">
        {pages.length === 0 && !showNewPage && (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <span className="mb-3 text-5xl">📄</span>
            <p className="text-gray-500">No pages yet. Add your first page!</p>
          </div>
        )}

        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          {pages.map((page) => (
            <PageCard
              key={page.id}
              page={page}
              onClick={() => router.push(`/notebook/${notebookId}/${page.id}`)}
              onDelete={() => handleDeletePage(page.id)}
            />
          ))}
        </div>
      </main>

      {/* New page form */}
      {showNewPage && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-sm rounded-xl bg-white p-6 shadow-xl">
            <h2 className="mb-4 text-lg font-semibold text-gray-900">New Page</h2>
            <form onSubmit={handleCreatePage} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Title</label>
                <input
                  autoFocus
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  required
                  placeholder="Lecture notes, Problem set…"
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-700 mb-2">Paper style</label>
                <div className="space-y-2">
                  {PAPER_OPTIONS.map((opt) => (
                    <label key={opt.value} className="flex cursor-pointer items-start gap-3 rounded-lg border p-3 hover:bg-gray-50 has-[:checked]:border-indigo-500 has-[:checked]:bg-indigo-50">
                      <input
                        type="radio"
                        name="paper_style"
                        value={opt.value}
                        checked={newStyle === opt.value}
                        onChange={() => setNewStyle(opt.value)}
                        className="mt-0.5 accent-indigo-600"
                      />
                      <div>
                        <span className="text-sm font-medium text-gray-900">{opt.label}</span>
                        <p className="text-xs text-gray-500">{opt.description}</p>
                      </div>
                    </label>
                  ))}
                </div>
              </div>

              <div className="flex gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => setShowNewPage(false)}
                  className="flex-1 rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving || !newTitle.trim()}
                  className="flex-1 rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                >
                  {saving ? "Creating…" : "Create"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
