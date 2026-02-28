"use client";

import { useEffect, useRef } from "react";
import { useWhiteboard } from "@/hooks/useWhiteboard";
import { animateStrokes } from "@/lib/strokeAnimator";
import type { StrokeData } from "@/types";

/**
 * Transparent canvas overlay on top of the tldraw canvas.
 * The AI's animated handwriting strokes are drawn here so they
 * don't interfere with the student's tldraw shapes.
 */
export default function WhiteboardOverlay() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const { pendingStrokes, clearPendingStrokes } = useWhiteboard();

  useEffect(() => {
    if (!pendingStrokes || !canvasRef.current) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    animateStrokes(ctx, pendingStrokes, () => {
      clearPendingStrokes();
    });
  }, [pendingStrokes, clearPendingStrokes]);

  return (
    <canvas
      ref={canvasRef}
      className="pointer-events-none absolute inset-0 z-10"
      style={{ width: "100%", height: "100%" }}
    />
  );
}
