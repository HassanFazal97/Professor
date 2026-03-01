"use client";

import { useCallback, useEffect, useRef } from "react";
import { Tldraw, exportToBlob, type Editor } from "@tldraw/tldraw";
import WhiteboardOverlay from "./WhiteboardOverlay";
import { useWhiteboard } from "@/hooks/useWhiteboard";
import type { BoardAction, StrokeData } from "@/types";

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
const FOLLOW_INSET_PX = 120;
const FOLLOW_MIN_COVERAGE = 0.14; // if writing is smaller than this fraction, zoom in
const FOLLOW_MAX_COVERAGE = 0.62; // if writing is larger than this fraction, zoom out
const FOLLOW_MARGIN_PX = 36;

type Bounds = { x: number; y: number; w: number; h: number };

function unionBounds(a: Bounds | null, b: Bounds | null): Bounds | null {
  if (!a) return b;
  if (!b) return a;
  const x1 = Math.min(a.x, b.x);
  const y1 = Math.min(a.y, b.y);
  const x2 = Math.max(a.x + a.w, b.x + b.w);
  const y2 = Math.max(a.y + a.h, b.y + b.h);
  return { x: x1, y: y1, w: x2 - x1, h: y2 - y1 };
}

function boundsFromStrokes(data: StrokeData): Bounds | null {
  let minX = Number.POSITIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;

  for (const stroke of data.strokes) {
    for (const p of stroke.points) {
      minX = Math.min(minX, p.x);
      minY = Math.min(minY, p.y);
      maxX = Math.max(maxX, p.x);
      maxY = Math.max(maxY, p.y);
    }
  }

  if (!Number.isFinite(minX) || !Number.isFinite(minY)) return null;
  const w = Math.max(140, maxX - minX);
  const h = Math.max(64, maxY - minY);
  return { x: minX - 20, y: minY - 18, w: w + 40, h: h + 36 };
}

function boundsFromAction(action: BoardAction): Bounds | null {
  if (action.type === "write") {
    const estW = Math.max(140, Math.min(520, action.content.length * 11));
    const estH = 58;
    return {
      x: action.position.x - 10,
      y: action.position.y - 12,
      w: estW,
      h: estH,
    };
  }
  if (action.type === "underline") {
    const { x, y, width, height } = action.target_area;
    return { x, y, w: width, h: Math.max(20, height + 12) };
  }
  return null;
}

function shouldRefocus(view: Bounds, target: Bounds): boolean {
  const inFrame =
    target.x >= view.x + FOLLOW_MARGIN_PX &&
    target.y >= view.y + FOLLOW_MARGIN_PX &&
    target.x + target.w <= view.x + view.w - FOLLOW_MARGIN_PX &&
    target.y + target.h <= view.y + view.h - FOLLOW_MARGIN_PX;

  const coverage = Math.max(target.w / view.w, target.h / view.h);
  const scaleBad = coverage < FOLLOW_MIN_COVERAGE || coverage > FOLLOW_MAX_COVERAGE;

  return !inFrame || scaleBad;
}

export default function Whiteboard() {
  const editorRef = useRef<Editor | null>(null);
  const lastSnapshotRef = useRef<number>(0);
  const { onSnapshotReady, pendingBoardActions, pendingStrokes, clearBoardActions, setEditor } = useWhiteboard();

  useEffect(() => {
    return () => setEditor(null);
  }, [setEditor]);

  // Process board actions from Ada whenever the queue changes
  useEffect(() => {
    if (!editorRef.current || pendingBoardActions.length === 0) return;
    const editor = editorRef.current;
    let focusBounds: Bounds | null = null;
    for (const action of pendingBoardActions) {
      applyBoardAction(editor, action);
      focusBounds = unionBounds(focusBounds, boundsFromAction(action));
    }
    if (focusBounds) {
      const view = editor.getViewportPageBounds();
      const viewBounds: Bounds = { x: view.x, y: view.y, w: view.w, h: view.h };
      if (shouldRefocus(viewBounds, focusBounds)) {
        editor.zoomToBounds(focusBounds, {
          inset: FOLLOW_INSET_PX,
          animation: { duration: 240 },
        });
      }
    }
    clearBoardActions();
  }, [pendingBoardActions, clearBoardActions]);

  // Keep Ada's incoming handwriting in frame at a readable zoom.
  useEffect(() => {
    if (!editorRef.current || !pendingStrokes) return;
    const editor = editorRef.current;
    const target = boundsFromStrokes(pendingStrokes);
    if (!target) return;

    const view = editor.getViewportPageBounds();
    const viewBounds: Bounds = { x: view.x, y: view.y, w: view.w, h: view.h };
    if (shouldRefocus(viewBounds, target)) {
      editor.zoomToBounds(target, {
        inset: FOLLOW_INSET_PX,
        animation: { duration: 240 },
      });
    }
  }, [pendingStrokes]);

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
