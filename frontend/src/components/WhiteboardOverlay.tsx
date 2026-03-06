"use client";

import { useEffect, useRef } from "react";
import { useWhiteboard } from "@/hooks/useWhiteboard";
import type { PaperStyle, Stroke, StrokeData } from "@/types";

const JITTER_PX = 0.35;
const DEFAULT_SPEED = 2.0;

interface Props {
  paperStyle?: PaperStyle;
}

/**
 * Transparent canvas overlay on top of the tldraw canvas.
 * Draws paper background (lined/graph) and Ada's animated handwriting strokes.
 */
export default function WhiteboardOverlay({ paperStyle = "blank" }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const cancelAnimationRef = useRef<(() => void) | null>(null);
  const activePartialRef = useRef<StrokeData | null>(null);
  const jitterRef = useRef<Map<string, { x: number; y: number }>>(new Map());
  const {
    pendingStrokes,
    clearPendingStrokes,
    setOverlayCanvas,
    editor,
    overlayResetVersion,
    completedStrokes,
    addCompletedStroke,
  } = useWhiteboard();

  useEffect(() => {
    if (canvasRef.current) setOverlayCanvas(canvasRef.current);
    return () => setOverlayCanvas(null);
  }, [setOverlayCanvas]);

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

  const drawPaperBackground = (
    ctx: CanvasRenderingContext2D,
    w: number,
    h: number,
  ) => {
    if (paperStyle === "lined") {
      // Horizontal ruled lines
      ctx.save();
      ctx.strokeStyle = "#dde8f4";
      ctx.lineWidth = 1;
      for (let y = 32; y < h; y += 32) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(w, y);
        ctx.stroke();
      }
      // Red margin line
      ctx.strokeStyle = "#ffb3b3";
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(64, 0);
      ctx.lineTo(64, h);
      ctx.stroke();
      ctx.restore();
    } else if (paperStyle === "graph") {
      ctx.save();
      // Minor grid lines
      ctx.strokeStyle = "#e8edf4";
      ctx.lineWidth = 0.5;
      for (let x = 0; x < w; x += 24) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, h);
        ctx.stroke();
      }
      for (let y = 0; y < h; y += 24) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(w, y);
        ctx.stroke();
      }
      // Major grid lines
      ctx.strokeStyle = "#c8d4e4";
      ctx.lineWidth = 1;
      for (let x = 0; x < w; x += 120) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, h);
        ctx.stroke();
      }
      for (let y = 0; y < h; y += 120) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(w, y);
        ctx.stroke();
      }
      ctx.restore();
    }
  };

  const renderScene = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Paper background first (screen-space, fixed)
    drawPaperBackground(ctx, canvas.width, canvas.height);

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

    for (const batch of completedStrokes) drawStrokeBatch(batch);
    if (activePartialRef.current) drawStrokeBatch(activePartialRef.current);
  };

  // Repaint on camera / editor changes
  useEffect(() => {
    if (!editor) {
      renderScene();
      return;
    }
    editor.on("change", () => {
      renderScene();
    });
    renderScene();
  }, [editor, completedStrokes, paperStyle]);

  // Re-render when paper style changes
  useEffect(() => {
    renderScene();
  }, [paperStyle]);

  // Clear overlay on board clear
  useEffect(() => {
    activePartialRef.current = null;
    jitterRef.current.clear();
    renderScene();
  }, [overlayResetVersion]);

  useEffect(() => {
    if (cancelAnimationRef.current) {
      cancelAnimationRef.current();
      cancelAnimationRef.current = null;
    }

    if (!pendingStrokes) {
      activePartialRef.current = null;
      renderScene();
      return;
    }

    const queue: Array<{ stroke: Stroke; pointIdx: number }> = [];
    pendingStrokes.strokes.forEach((stroke) => {
      stroke.points.forEach((_, idx) => {
        queue.push({ stroke, pointIdx: idx });
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
    activePartialRef.current = { ...pendingStrokes, strokes: activePoints };

    const tick = () => {
      if (cancelled || !activePartialRef.current) return;

      const pointsThisFrame = Math.max(1, Math.round(speed * 2));
      for (let i = 0; i < pointsThisFrame && index < queue.length; i++) {
        const item = queue[index];
        const strokeIdx = pendingStrokes.strokes.indexOf(item.stroke);
        if (strokeIdx >= 0) {
          activePartialRef.current.strokes[strokeIdx].points.push(
            item.stroke.points[item.pointIdx],
          );
        }
        index++;
      }

      renderScene();

      if (index < queue.length) {
        requestAnimationFrame(tick);
      } else {
        // Move to completed strokes in Zustand (replaces completedRef)
        addCompletedStroke(pendingStrokes);
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
