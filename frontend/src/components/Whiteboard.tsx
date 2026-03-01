"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Tldraw, exportToBlob, type Editor } from "@tldraw/tldraw";
import WhiteboardOverlay from "./WhiteboardOverlay";
import { useWhiteboard } from "@/hooks/useWhiteboard";
import type { BoardAction } from "@/types";

const HEX_TO_TLDRAW: Record<string, string> = {
  "#FF0000": "red",
  "#0000FF": "blue",
  "#00AA00": "green",
  "#000000": "black",
};

function toTldrawColor(hex: string): string {
  return HEX_TO_TLDRAW[hex.toUpperCase()] ?? "black";
}

const AI_SHAPE_META = { createdBy: "ai-tutor" };

function applyBoardAction(editor: Editor, action: BoardAction): void {
  switch (action.type) {
    case "write": {
      editor.createShapes([
        {
          type: "text",
          x: action.position.x,
          y: action.position.y,
          meta: AI_SHAPE_META,
          props: {
            text: action.content,
            color: toTldrawColor(action.color),
            size: "m",
            font: "sans",
            autoSize: true,
            w: 300,
          } as any,
        },
      ]);
      break;
    }

    case "underline": {
      const { x, y, width, height } = action.target_area;
      editor.createShapes([
        {
          type: "geo",
          x,
          y: y + height,
          meta: AI_SHAPE_META,
          props: {
            geo: "rectangle",
            w: width,
            h: 3,
            color: toTldrawColor(action.color),
            fill: "solid",
          } as any,
        },
      ]);
      break;
    }

    case "clear": {
      const ids = [...editor.getCurrentPageShapeIds()];
      if (ids.length > 0) editor.deleteShapes(ids);
      useWhiteboard.getState().cancelStrokes();
      useWhiteboard.getState().clearOverlay();
      break;
    }
  }
}

const SNAPSHOT_MIN_INTERVAL_MS = 2500;

export default function Whiteboard() {
  const editorRef = useRef<Editor | null>(null);
  const lastSnapshotRef = useRef<number>(0);
  const [stylePanelOpen, setStylePanelOpen] = useState(false);
  const { onSnapshotReady, pendingBoardActions, clearBoardActions, setEditor } = useWhiteboard();

  useEffect(() => {
    return () => setEditor(null);
  }, [setEditor]);

  // Process board actions from Ada whenever the queue changes
  useEffect(() => {
    if (!editorRef.current || pendingBoardActions.length === 0) return;
    const editor = editorRef.current;
    for (const action of pendingBoardActions) {
      applyBoardAction(editor, action);
    }
    clearBoardActions();
  }, [pendingBoardActions, clearBoardActions]);

  const handleMount = useCallback(
    (editor: Editor) => {
      editorRef.current = editor;
      setEditor(editor);

      // Fix the viewport — no user zoom or pan. The overlay canvas and tldraw
      // page coordinates share the same space only when the camera is locked at
      // the identity transform, so composite snapshots sent to the LLM are accurate.
      editor.setCamera({ x: 0, y: 0, z: 0.8 });
      editor.setCameraOptions({ isLocked: true });

      // Trigger snapshot after a short drawing pause
      let idleTimer: ReturnType<typeof setTimeout> | null = null;
      editor.on("change", () => {
        if (idleTimer) clearTimeout(idleTimer);
        idleTimer = setTimeout(async () => {
          await captureSnapshot(editor);
        }, 1400);
      });
    },
    [setEditor],
  );

  const captureSnapshot = async (editor: Editor) => {
    const now = Date.now();
    if (now - lastSnapshotRef.current < SNAPSHOT_MIN_INTERVAL_MS) return;
    lastSnapshotRef.current = now;
    try {
      // Only include shapes the student drew — not AI-placed text shapes
      const allIds = [...editor.getCurrentPageShapeIds()];
      const ids = allIds.filter((id) => {
        const shape = editor.getShape(id) as any;
        return shape?.meta?.createdBy !== "ai-tutor";
      });
      if (ids.length === 0) return;

      const container = editor.getContainer();
      const W = container.offsetWidth;
      const H = container.offsetHeight;

      // Composite canvas for vision: white background -> student shapes only.
      // Excluding AI overlay strokes prevents the model from reacting to its own writing.
      const composite = document.createElement("canvas");
      composite.width = W;
      composite.height = H;
      const ctx = composite.getContext("2d")!;
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, W, H);

      if (ids.length > 0) {
        const viewBounds = editor.getViewportPageBounds();
        const blob = await exportToBlob({
          editor,
          ids,
          format: "png",
          opts: { bounds: viewBounds, scale: 1 },
        });
        await new Promise<void>((resolve) => {
          const img = new Image();
          const url = URL.createObjectURL(blob);
          img.onload = () => {
            ctx.drawImage(img, 0, 0, W, H);
            URL.revokeObjectURL(url);
            resolve();
          };
          img.src = url;
        });
      }

      // Compute the bottommost world-y of student shapes so the backend can
      // avoid placing Ada's writing on top of the student's work.
      let studentMaxY = 0;
      for (const id of ids) {
        const bounds = editor.getShapePageBounds(id);
        if (bounds) studentMaxY = Math.max(studentMaxY, bounds.maxY);
      }

      const base64 = composite.toDataURL("image/png").split(",")[1];
      onSnapshotReady(base64, W, H, studentMaxY > 0 ? Math.ceil(studentMaxY) : undefined);
    } catch (err) {
      console.warn("Snapshot failed:", err);
    }
  };

  return (
    <div className={`tldraw-container ${stylePanelOpen ? "style-panel-open" : ""}`}>
      <Tldraw onMount={handleMount} />
      <WhiteboardOverlay />
      <button
        type="button"
        onClick={() => setStylePanelOpen((prev) => !prev)}
        aria-pressed={stylePanelOpen}
        title={stylePanelOpen ? "Hide style panel" : "Show style panel"}
        className="absolute right-2 top-2 z-20 inline-flex h-9 w-9 items-center justify-center rounded-md bg-white text-gray-700 shadow-sm ring-1 ring-gray-200 hover:bg-gray-50"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="currentColor"
          className="h-5 w-5"
        >
          <path d="M3 17.25V21h3.75l11-11.03-3.75-3.75L3 17.25zm14.71-9.04c.39-.39.39-1.02 0-1.41l-2.5-2.5a.9959.9959 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.99-1.67z" />
        </svg>
      </button>
    </div>
  );
}
