"use client";

import { useEffect, useRef } from "react";
import { useWhiteboard } from "@/hooks/useWhiteboard";
import { animateStrokes } from "@/lib/strokeAnimator";

/**
 * Transparent canvas overlay on top of the tldraw canvas.
 * The AI's animated handwriting strokes are drawn here so they
 * don't interfere with the student's tldraw shapes.
 */
export default function WhiteboardOverlay() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const cancelRef = useRef<(() => void) | null>(null);
  const { pendingStrokes, clearPendingStrokes, setOverlayCanvas } = useWhiteboard();

  // Register this canvas with the store so Whiteboard.tsx can include it
  // in composite snapshots sent to the LLM for vision.
  useEffect(() => {
    if (canvasRef.current) setOverlayCanvas(canvasRef.current);
    return () => setOverlayCanvas(null);
  }, [setOverlayCanvas]);

  // Keep the canvas bitmap buffer in sync with its CSS layout size.
  // Without this, the default 300×150 buffer causes strokes to be
  // stretched and clipped.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const sync = () => {
      canvas.width = canvas.offsetWidth;
      canvas.height = canvas.offsetHeight;
    };

    sync();
    const observer = new ResizeObserver(sync);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    // Cancel any in-progress animation first.
    // On barge-in, cancelStrokes() sets pendingStrokes → null, which re-runs
    // this effect. The cancelled RAF loop stops without calling onDone.
    if (cancelRef.current) {
      cancelRef.current();
      cancelRef.current = null;
    }

    const canvas = canvasRef.current;
    if (!pendingStrokes || !canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    cancelRef.current = animateStrokes(ctx, pendingStrokes, () => {
      cancelRef.current = null;
      clearPendingStrokes(); // dequeue next stroke batch when this one finishes
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
