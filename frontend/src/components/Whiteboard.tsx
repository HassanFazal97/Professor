"use client";

import { useCallback, useEffect, useRef } from "react";
import { Tldraw, exportToBlob, type Editor } from "@tldraw/tldraw";
import WhiteboardOverlay from "./WhiteboardOverlay";
import { useWhiteboard } from "@/hooks/useWhiteboard";
import type { BoardAction } from "@/types";

// Map our hex color conventions to tldraw's named color system
const HEX_TO_TLDRAW: Record<string, string> = {
  "#FF0000": "red",
  "#0000FF": "blue",
  "#00AA00": "green",
  "#000000": "black",
};

function toTldrawColor(hex: string): string {
  return HEX_TO_TLDRAW[hex.toUpperCase()] ?? "black";
}

function applyBoardAction(editor: Editor, action: BoardAction): void {
  switch (action.type) {
    case "write": {
      editor.createShapes([
        {
          type: "text",
          x: action.position.x,
          y: action.position.y,
          props: {
            text: action.content,
            color: toTldrawColor(action.color),
            size: "m",
            font: "draw",
            autoSize: true,
            w: 300,
          } as any,
        },
      ]);
      break;
    }

    case "underline": {
      const { x, y, width, height } = action.target_area;
      // Draw a thin filled rectangle along the bottom edge of the target area
      editor.createShapes([
        {
          type: "geo",
          x,
          y: y + height,
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
      // Also wipe Ada's handwriting strokes and stop any in-progress animation
      useWhiteboard.getState().cancelStrokes();
      useWhiteboard.getState().clearOverlay();
      break;
    }
  }
}

const SNAPSHOT_MIN_INTERVAL_MS = 2500; // don't send more than once every 2.5s

export default function Whiteboard() {
  const editorRef = useRef<Editor | null>(null);
  const lastSnapshotRef = useRef<number>(0);
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

  const handleMount = useCallback((editor: Editor) => {
    editorRef.current = editor;
    setEditor(editor);

    // Trigger snapshot on short drawing pause for better responsiveness
    let idleTimer: ReturnType<typeof setTimeout> | null = null;
    editor.on("change", () => {
      if (idleTimer) clearTimeout(idleTimer);
      idleTimer = setTimeout(async () => {
        await captureSnapshot(editor);
      }, 1400);
    });
  }, [setEditor]);

  const captureSnapshot = async (editor: Editor) => {
    const now = Date.now();
    if (now - lastSnapshotRef.current < SNAPSHOT_MIN_INTERVAL_MS) return;
    lastSnapshotRef.current = now;
    try {
      const ids = [...editor.getCurrentPageShapeIds()];
      const overlayCanvas = useWhiteboard.getState().overlayCanvas;

      // Nothing to capture yet
      if (ids.length === 0 && !overlayCanvas) return;

      const container = editor.getContainer();
      const W = container.offsetWidth;
      const H = container.offsetHeight;

      // Composite canvas: white background → tldraw shapes → Ada's overlay strokes
      const composite = document.createElement("canvas");
      composite.width = W;
      composite.height = H;
      const ctx = composite.getContext("2d")!;
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, W, H);

      // Draw tldraw shapes using the current viewport bounds.
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

      // Draw Ada's accumulated handwriting strokes on top
      if (overlayCanvas) {
        ctx.drawImage(overlayCanvas, 0, 0, W, H);
      }

      const base64 = composite.toDataURL("image/png").split(",")[1];
      onSnapshotReady(base64, W, H);
    } catch (err) {
      console.warn("Snapshot failed:", err);
    }
  };

  return (
    <div className="tldraw-container">
      <Tldraw onMount={handleMount} />
      <WhiteboardOverlay />
    </div>
  );
}
