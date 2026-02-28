"use client";

import { useCallback, useRef } from "react";
import { Tldraw, exportToBlob, type Editor } from "@tldraw/tldraw";
import WhiteboardOverlay from "./WhiteboardOverlay";
import { useWhiteboard } from "@/hooks/useWhiteboard";

export default function Whiteboard() {
  const editorRef = useRef<Editor | null>(null);
  const { onSnapshotReady } = useWhiteboard();

  const handleMount = useCallback((editor: Editor) => {
    editorRef.current = editor;

    // Trigger snapshot on drawing pause (2-3s idle)
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
