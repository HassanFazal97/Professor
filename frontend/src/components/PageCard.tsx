"use client";

import type { PageOut } from "@/types";

const STYLE_LABELS: Record<string, string> = {
  blank: "Blank",
  lined: "Lined",
  graph: "Graph",
};

interface Props {
  page: PageOut;
  onClick: () => void;
  onDelete: () => void;
}

export default function PageCard({ page, onClick, onDelete }: Props) {
  return (
    <div
      onClick={onClick}
      className="group relative cursor-pointer rounded-xl bg-white p-5 shadow-sm ring-1 ring-gray-200 hover:shadow-md transition-shadow"
    >
      <div className="mb-3 flex items-center gap-2">
        <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-indigo-100 text-xs font-bold text-indigo-700">
          {page.page_number}
        </span>
        <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500">
          {STYLE_LABELS[page.paper_style] ?? page.paper_style}
        </span>
      </div>
      <h3 className="font-medium text-gray-900 truncate">{page.title}</h3>
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); onDelete(); }}
        className="absolute right-3 top-3 hidden rounded-md p-1 text-gray-400 hover:bg-red-50 hover:text-red-500 group-hover:block"
        title="Delete page"
      >
        <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
          <path
            fillRule="evenodd"
            d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z"
            clipRule="evenodd"
          />
        </svg>
      </button>
    </div>
  );
}
