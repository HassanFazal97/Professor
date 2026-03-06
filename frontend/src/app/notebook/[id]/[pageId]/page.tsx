"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import AudioManager from "@/components/AudioManager";
import SessionControls from "@/components/SessionControls";
import TutorPanel from "@/components/TutorPanel";
import Whiteboard from "@/components/Whiteboard";
import { api } from "@/lib/api";
import type { PageOut } from "@/types";

export default function PageView() {
  const params = useParams();
  const notebookId = params.id as string;
  const pageId = params.pageId as string;
  const router = useRouter();
  const [page, setPage] = useState<PageOut | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.pages.get(pageId).then((p) => {
      setPage(p);
      setLoading(false);
    }).catch(() => {
      router.push(`/notebook/${notebookId}`);
    });
  }, [pageId, notebookId, router]);

  if (loading || !page) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent" />
      </div>
    );
  }

  return (
    <main className="flex h-screen w-screen overflow-hidden">
      {/* Left panel */}
      <aside className="flex w-80 flex-shrink-0 flex-col border-r border-gray-200 bg-white shadow-sm">
        {/* Back breadcrumb */}
        <div className="flex items-center gap-1 border-b border-gray-100 px-4 py-2 text-xs text-gray-500">
          <button
            onClick={() => router.push(`/notebook/${notebookId}`)}
            className="hover:text-indigo-600 hover:underline"
          >
            Back
          </button>
          <span>/</span>
          <span className="truncate font-medium text-gray-700">{page.title}</span>
        </div>
        <TutorPanel />
        <div className="border-t border-gray-200 p-3">
          <SessionControls pageId={pageId} />
        </div>
      </aside>

      {/* Right panel — whiteboard */}
      <section className="relative flex-1 overflow-hidden">
        <Whiteboard pageId={pageId} paperStyle={page.paper_style} />
      </section>

      <AudioManager />
    </main>
  );
}
