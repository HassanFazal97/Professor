"use client";

import { useEffect, useRef } from "react";
import { useWhiteboard } from "@/hooks/useWhiteboard";
import type { Stroke, StrokeData } from "@/types";

const JITTER_PX = 0.35;
const DEFAULT_SPEED = 2.0;

/**
 * Transparent canvas overlay on top of the tldraw canvas.
 * The AI's animated handwriting strokes are drawn here so they
 * don't interfere with the student's tldraw shapes.
 */
export default function WhiteboardOverlay() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const cancelAnimationRef = useRef<(() => void) | null>(null);
  const completedRef = useRef<StrokeData[]>([]);
  const activePartialRef = useRef<StrokeData | null>(null);
  const jitterRef = useRef<Map<string, { x: number; y: number }>>(new Map());
  const {
    pendingStrokes,
    clearPendingStrokes,
    setOverlayCanvas,
    editor,
    overlayResetVersion,
  } = useWhiteboard();


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

  const renderScene = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const drawStrokeBatch = (batch: StrokeData) => {
      for (const stroke of batch.strokes) {
        if (!stroke.points.length) continue;
        ctx.beginPath();
        let started = false;

        for (let i = 0; i < stroke.points.length; i++) {
          const p = stroke.points[i];
          const screen = editor
            ? editor.pageToScreen({ x: p.x, y: p.y })
            : { x: p.x, y: p.y };

          const key = `${stroke.color}:${stroke.width}:${p.x.toFixed(2)}:${p.y.toFixed(2)}:${i}`;
          let j = jitterRef.current.get(key);
          if (!j) {
            j = {
              x: (Math.random() - 0.5) * 2 * JITTER_PX,
              y: (Math.random() - 0.5) * 2 * JITTER_PX,
            };
            jitterRef.current.set(key, j);
          }

          const x = screen.x + j.x;
          const y = screen.y + j.y;

          ctx.lineWidth = stroke.width * (0.94 + p.pressure * 0.12);
          ctx.strokeStyle = stroke.color;
          ctx.lineCap = "round";
          ctx.lineJoin = "round";

          if (!started) {
            ctx.moveTo(x, y);
            started = true;
          } else {
            ctx.lineTo(x, y);
          }
        }

        if (started) ctx.stroke();
      }
    };

    for (const batch of completedRef.current) drawStrokeBatch(batch);
    if (activePartialRef.current) drawStrokeBatch(activePartialRef.current);
  };

  // Repaint on camera / editor changes so world-space strokes stay aligned.
  useEffect(() => {
    if (!editor) {
      renderScene();
      return;
    }
    editor.on("change", () => {
      renderScene();
    });
    renderScene();
  }, [editor]);

  // Clear vector/raster caches when the orchestrator issues a board clear.
  useEffect(() => {
    completedRef.current = [];
    activePartialRef.current = null;
    jitterRef.current.clear();
    renderScene();
  }, [overlayResetVersion]);

  useEffect(() => {
    // Cancel any in-progress animation first.
    if (cancelAnimationRef.current) {
      cancelAnimationRef.current();
      cancelAnimationRef.current = null;
    }

    if (!pendingStrokes) {
      activePartialRef.current = null;
      renderScene();
      return;
    }

    const queue: Array<{ stroke: Stroke; pointIdx: number; isFirst: boolean }> = [];
    pendingStrokes.strokes.forEach((stroke) => {
      stroke.points.forEach((_, idx) => {
        queue.push({ stroke, pointIdx: idx, isFirst: idx === 0 });
      });
    });

    if (!queue.length) {
      clearPendingStrokes();
      return;
    }

    const speed = pendingStrokes.animation_speed * DEFAULT_SPEED;
    let index = 0;
    let cancelled = false;
    const activePoints = pendingStrokes.strokes.map((s) => ({
      ...s,
      points: [] as typeof s.points,
    }));
    activePartialRef.current = {
      ...pendingStrokes,
      strokes: activePoints,
    };

    const tick = () => {
      if (cancelled || !activePartialRef.current) return;

      const pointsThisFrame = Math.max(1, Math.round(speed * 2));
      for (let i = 0; i < pointsThisFrame && index < queue.length; i++) {
        const item = queue[index];
        const strokeIdx = pendingStrokes.strokes.indexOf(item.stroke);
        if (strokeIdx >= 0) {
          const sourcePoint = item.stroke.points[item.pointIdx];
          activePartialRef.current.strokes[strokeIdx].points.push(sourcePoint);
        }
        index++;
      }

      renderScene();

      if (index < queue.length) {
        requestAnimationFrame(tick);
      } else {
        // Keep completed strokes on the overlay canvas so they render
        // identically to the animation — no hand-off to tldraw which
        // applies its own smoothing/pressure model and causes a visual shift.
        completedRef.current.push(pendingStrokes);
        activePartialRef.current = null;
        renderScene();
        clearPendingStrokes();
      }
    };

    requestAnimationFrame(tick);

    cancelAnimationRef.current = () => {
      cancelled = true;
    };

    return () => {
      cancelled = true;
    };
  }, [pendingStrokes, clearPendingStrokes, editor]);

  return (
    <canvas
      ref={canvasRef}
      className="pointer-events-none absolute inset-0 z-10"
      style={{ width: "100%", height: "100%" }}
    />
  );
}
