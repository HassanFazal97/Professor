"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useNotebooks } from "@/hooks/useNotebooks";
import NotebookCard from "@/components/NotebookCard";
import NewNotebookModal from "@/components/NewNotebookModal";
import type { NotebookCreateBody } from "@/types";

export default function LibraryPage() {
  const router = useRouter();
  const { notebooks, isLoading, error, fetchNotebooks, createNotebook, deleteNotebook } =
    useNotebooks();
  const [showModal, setShowModal] = useState(false);

  useEffect(() => {
    fetchNotebooks();
  }, [fetchNotebooks]);

  const handleCreate = async (body: NotebookCreateBody) => {
    const nb = await createNotebook(body);
    router.push(`/notebook/${nb.id}`);
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this notebook and all its pages?")) return;
    await deleteNotebook(id);
  };

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <div className="mb-6 flex items-center justify-between">
        <h2 className="text-xl font-semibold text-gray-900">My Notebooks</h2>
        <button
          onClick={() => setShowModal(true)}
          className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
        >
          + New Notebook
        </button>
      </div>

      {isLoading && (
        <div className="flex justify-center py-12">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent" />
        </div>
      )}

      {error && (
        <p className="rounded-md bg-red-50 p-4 text-sm text-red-600">{error}</p>
      )}

      {!isLoading && notebooks.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <span className="mb-3 text-5xl">📒</span>
          <p className="text-gray-500">No notebooks yet. Create your first one!</p>
        </div>
      )}

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
        {notebooks.map((nb) => (
          <NotebookCard
            key={nb.id}
            notebook={nb}
            onClick={() => router.push(`/notebook/${nb.id}`)}
            onDelete={() => handleDelete(nb.id)}
          />
        ))}
      </div>

      {showModal && (
        <NewNotebookModal
          onClose={() => setShowModal(false)}
          onCreate={handleCreate}
        />
      )}
    </div>
  );
}
