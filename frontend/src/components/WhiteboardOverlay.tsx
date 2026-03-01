"use client";

import { useEffect, useRef } from "react";
import { useWhiteboard } from "@/hooks/useWhiteboard";
import type { Stroke, StrokeData } from "@/types";

const JITTER_PX = 0.35;
const DEFAULT_SPEED = 1.0;

const HEX_TO_TLDRAW_COLOR: Record<string, "black" | "blue" | "red" | "green"> = {
  "#000000": "black",
  "#0000FF": "blue",
  "#FF0000": "red",
  "#00AA00": "green",
};

function toTldrawColor(hex: string): "black" | "blue" | "red" | "green" {
  return HEX_TO_TLDRAW_COLOR[(hex || "").toUpperCase()] ?? "black";
}

const AI_SHAPE_META = { createdBy: "ai-tutor" };

function toTldrawSize(_width: number): "s" {
  // Force the thinnest pen size for legibility.
  return "s";
}

function sizeToRenderWidth(size: "s" | "m" | "l" | "xl"): number {
  switch (size) {
    case "s":
      return 1.2;
    case "m":
      return 1.6;
    case "l":
      return 2.2;
    case "xl":
      return 2.8;
  }
}

function simplifyStrokePoints(
  points: Array<{ x: number; y: number; pressure: number }>,
): Array<{ x: number; y: number; pressure: number }> {
  if (points.length <= 2) return points;

  const simplified: Array<{ x: number; y: number; pressure: number }> = [points[0]];
  let prev = points[0];

  // Keep points only when they move enough in page space.
  // This prevents dense point clouds from producing "paint blob" letters.
  const MIN_DIST = 1.9;
  const MIN_DIST_SQ = MIN_DIST * MIN_DIST;

  for (let i = 1; i < points.length - 1; i++) {
    const p = points[i];
    const dx = p.x - prev.x;
    const dy = p.y - prev.y;
    const distSq = dx * dx + dy * dy;
    if (distSq >= MIN_DIST_SQ) {
      simplified.push(p);
      prev = p;
    }
  }

  simplified.push(points[points.length - 1]);
  return simplified;
}

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

  const commitStrokeBatchToEditor = (batch: StrokeData) => {
    if (!editor) return;
    const shapes: any[] = [];

    for (const stroke of batch.strokes) {
      if (!stroke.points.length) continue;
      const simplifiedPoints = simplifyStrokePoints(stroke.points);
      if (simplifiedPoints.length < 2) continue;

      let minX = Number.POSITIVE_INFINITY;
      let minY = Number.POSITIVE_INFINITY;
      for (const p of simplifiedPoints) {
        minX = Math.min(minX, p.x);
        minY = Math.min(minY, p.y);
      }
      if (!Number.isFinite(minX) || !Number.isFinite(minY)) continue;

      const segmentPoints = simplifiedPoints.map((p) => ({
        x: p.x - minX,
        y: p.y - minY,
        // Lower pressure -> thinner stroke envelope in tldraw's draw shape.
        z: Math.max(0.18, Math.min(0.38, p.pressure * 0.45)),
      }));

      const size = toTldrawSize(stroke.width);
      shapes.push({
        type: "draw",
        x: minX,
        y: minY,
        meta: AI_SHAPE_META,
        props: {
          color: toTldrawColor(stroke.color),
          fill: "none",
          dash: "draw",
          size,
          segments: [{ type: "free", points: segmentPoints }],
          isComplete: true,
          isClosed: false,
          isPen: true,
          scale: 1,
        },
      });
    }

    if (shapes.length > 0) {
      editor.createShapes(shapes);
    }
  };

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
        const size = toTldrawSize(stroke.width);
        const baseWidth = sizeToRenderWidth(size);
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

          // Match tldraw-like pen thickness during animation so the transition
          // to committed draw shapes is visually consistent.
          ctx.lineWidth = baseWidth * (0.94 + p.pressure * 0.12);
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
        if (editor) {
          commitStrokeBatchToEditor(pendingStrokes);
        } else {
          completedRef.current.push(pendingStrokes);
        }
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
