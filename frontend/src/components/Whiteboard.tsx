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
      break;
    }
  }
}

export default function Whiteboard() {
  const editorRef = useRef<Editor | null>(null);
  const { onSnapshotReady, pendingBoardActions, clearBoardActions } = useWhiteboard();

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

    // Trigger snapshot on 2.5s drawing pause
    let idleTimer: ReturnType<typeof setTimeout> | null = null;
    editor.on("change", () => {
      if (idleTimer) clearTimeout(idleTimer);
      idleTimer = setTimeout(async () => {
        await captureSnapshot(editor);
      }, 2500);
    });
  }, []);

  const captureSnapshot = async (editor: Editor) => {
    try {
      const ids = [...editor.getCurrentPageShapeIds()];
      if (ids.length === 0) return;
      const blob = await exportToBlob({
        editor,
        ids,
        format: "png",
        opts: { scale: 0.5 },
      });
      const reader = new FileReader();
      reader.onload = () => {
        const base64 = (reader.result as string).split(",")[1];
        onSnapshotReady(base64);
      };
      reader.readAsDataURL(blob);
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
