import type { Stroke, StrokeData, StrokePoint } from "@/types";

const JITTER_PX = 1; // ±1px organic feel
const DEFAULT_SPEED = 1.0; // points per frame multiplier

/**
 * Animate a set of AI handwriting strokes onto a canvas context.
 *
 * Uses requestAnimationFrame to draw stroke points incrementally.
 * Applies ±1px jitter per point for an organic handwriting feel.
 *
 * @param ctx     2D canvas context to draw on
 * @param data    StrokeData from the backend
 * @param onDone  Callback invoked when all strokes finish animating naturally
 * @returns       A cancel function — call it to stop the animation immediately.
 *                onDone is NOT called when cancelled.
 */
export function animateStrokes(
  ctx: CanvasRenderingContext2D,
  data: StrokeData,
  onDone?: () => void,
): () => void {
  const { strokes, animation_speed } = data;
  if (!strokes.length) {
    onDone?.();
    return () => {};
  }

  // Flatten all strokes into an ordered animation queue
  type AnimPoint = { point: StrokePoint; stroke: Stroke; isFirst: boolean };
  const queue: AnimPoint[] = [];

  for (const stroke of strokes) {
    stroke.points.forEach((point, idx) => {
      queue.push({ point, stroke, isFirst: idx === 0 });
    });
  }

  let index = 0;
  let cancelled = false;
  const speed = animation_speed * DEFAULT_SPEED;

  const draw = () => {
    if (cancelled) return; // stop without calling onDone

    // Draw multiple points per frame based on speed
    const pointsThisFrame = Math.max(1, Math.round(speed * 2));

    for (let i = 0; i < pointsThisFrame && index < queue.length; i++) {
      const { point, stroke, isFirst } = queue[index];
      const jx = (Math.random() - 0.5) * 2 * JITTER_PX;
      const jy = (Math.random() - 0.5) * 2 * JITTER_PX;
      const x = point.x + jx;
      const y = point.y + jy;

      ctx.lineWidth = stroke.width * (0.8 + point.pressure * 0.4);
      ctx.strokeStyle = stroke.color;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";

      if (isFirst) {
        ctx.beginPath();
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
        ctx.stroke();
      }

      index++;
    }

    if (index < queue.length) {
      requestAnimationFrame(draw);
    } else {
      onDone?.();
    }
  };

  requestAnimationFrame(draw);

  return () => {
    cancelled = true;
  };
}
