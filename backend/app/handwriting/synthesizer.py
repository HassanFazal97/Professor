import math
import random
import ssl
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTFont

# Patrick Hand is a Google Font (OFL license) — clean printed handwriting style.
_FONT_URL = (
    "https://cdn.jsdelivr.net/gh/google/fonts@main"
    "/ofl/patrickhand/PatrickHand-Regular.ttf"
)
_FONT_PATH = Path(__file__).parent / "PatrickHand-Regular.ttf"

# Visual cap height on the whiteboard canvas (px).
_TARGET_CAP_HEIGHT_PX = 40

# Oversample factor for rasterizing glyphs before skeletonizing.
# Higher = smoother skeleton but more memory/time per glyph.
_OVERSAMPLE = 4


# ── Wire-format dataclasses (must match frontend StrokeData type) ─────────────


@dataclass
class StrokePoint:
    x: float
    y: float
    pressure: float = 0.8


@dataclass
class Stroke:
    points: list[StrokePoint]
    color: str = "#000000"
    width: float = 2.0


@dataclass
class StrokeData:
    strokes: list[Stroke]
    position: dict  # {"x": float, "y": float}
    animation_speed: float = 1.0

    def to_dict(self) -> dict:
        return {
            "strokes": [
                {
                    "points": [
                        {"x": p.x, "y": p.y, "pressure": p.pressure}
                        for p in stroke.points
                    ],
                    "color": stroke.color,
                    "width": stroke.width,
                }
                for stroke in self.strokes
            ],
            "position": self.position,
            "animation_speed": self.animation_speed,
        }


# ── Bezier sampling helpers ────────────────────────────────────────────────────


def _sample_quadratic(p0, p1, p2, n: int = 3) -> list[tuple]:
    pts = []
    for i in range(n + 1):
        t = i / n
        mt = 1 - t
        x = mt * mt * p0[0] + 2 * mt * t * p1[0] + t * t * p2[0]
        y = mt * mt * p0[1] + 2 * mt * t * p1[1] + t * t * p2[1]
        pts.append((x, y))
    return pts


def _sample_cubic(p0, p1, p2, p3, n: int = 4) -> list[tuple]:
    pts = []
    for i in range(n + 1):
        t = i / n
        mt = 1 - t
        x = mt**3 * p0[0] + 3 * mt**2 * t * p1[0] + 3 * mt * t**2 * p2[0] + t**3 * p3[0]
        y = mt**3 * p0[1] + 3 * mt**2 * t * p1[1] + 3 * mt * t**2 * p2[1] + t**3 * p3[1]
        pts.append((x, y))
    return pts


# ── Convert RecordingPen value → list of contours ────────────────────────────


def _recording_to_contours(value: list) -> list[list[tuple]]:
    """Convert a RecordingPen value list into contours (lists of (x,y) font-unit points)."""
    contours: list[list[tuple]] = []
    current: list[tuple] = []

    for op, args in value:
        if op == "moveTo":
            if len(current) > 1:
                contours.append(current)
            current = [args[0]]

        elif op == "lineTo":
            current.append(args[0])

        elif op == "qCurveTo":
            pts = list(args)
            start = current[-1] if current else pts[0]
            while len(pts) > 2:
                p1 = pts[0]
                p2 = ((pts[0][0] + pts[1][0]) / 2.0, (pts[0][1] + pts[1][1]) / 2.0)
                current.extend(_sample_quadratic(start, p1, p2)[1:])
                start = p2
                pts.pop(0)
            if len(pts) == 2:
                current.extend(_sample_quadratic(start, pts[0], pts[1])[1:])
            elif len(pts) == 1:
                current.append(pts[0])

        elif op == "curveTo":
            p0 = current[-1] if current else args[0]
            current.extend(_sample_cubic(p0, args[0], args[1], args[2])[1:])

        elif op in ("closePath", "endPath"):
            if len(current) > 1:
                contours.append(current)
            current = []

    if len(current) > 1:
        contours.append(current)

    return contours


# ── Skeleton helpers ───────────────────────────────────────────────────────────


def _signed_area(contour: list) -> float:
    """
    Signed polygon area in font coordinate space (y-up).
    Positive → counter-clockwise (outer contour).
    Negative → clockwise (inner counter/hole).
    """
    n = len(contour)
    if n < 3:
        return 0.0
    return (
        sum(
            contour[i][0] * contour[(i + 1) % n][1]
            - contour[(i + 1) % n][0] * contour[i][1]
            for i in range(n)
        )
        / 2.0
    )


def _zhang_suen_thin(img: np.ndarray) -> np.ndarray:
    """
    Vectorized Zhang-Suen thinning: reduces a filled binary image to a
    1-pixel-wide skeleton representing the centerline of each stroke.
    """
    img = img.astype(bool)

    def _step(img: np.ndarray, even_step: bool):
        u = img.astype(np.uint8)
        p = np.pad(u, 1)
        P2 = p[0:-2, 1:-1]   # N
        P3 = p[0:-2, 2:]     # NE
        P4 = p[1:-1, 2:]     # E
        P5 = p[2:,   2:]     # SE
        P6 = p[2:,   1:-1]   # S
        P7 = p[2:,   0:-2]   # SW
        P8 = p[1:-1, 0:-2]   # W
        P9 = p[0:-2, 0:-2]   # NW

        B = P2 + P3 + P4 + P5 + P6 + P7 + P8 + P9

        # Count 0→1 transitions in the cyclic sequence P2…P9,P2
        seq = np.stack([P2, P3, P4, P5, P6, P7, P8, P9, P2], axis=0)
        A = np.sum((seq[:-1] == 0) & (seq[1:] == 1), axis=0)

        cond12 = (B >= 2) & (B <= 6) & (A == 1)
        if even_step:
            cond34 = (P2 * P4 * P6 == 0) & (P4 * P6 * P8 == 0)
        else:
            cond34 = (P2 * P4 * P8 == 0) & (P2 * P6 * P8 == 0)

        remove = img & cond12 & cond34
        return img & ~remove, bool(np.any(remove))

    changed = True
    while changed:
        img, c1 = _step(img, even_step=True)
        img, c2 = _step(img, even_step=False)
        changed = c1 or c2

    return img


def _trace_skeleton(skel: np.ndarray) -> list[list[tuple[float, float]]]:
    """
    Walk skeleton pixels into ordered lists of (x_pixel, y_pixel) points.
    Starts from endpoint pixels (single neighbor) so each stroke is traced
    from tip to tip.  Prefers to continue in the same direction at each step
    to produce smoother curves.
    """
    ys, xs = np.where(skel)
    if len(ys) == 0:
        return []

    pt_set: set[tuple[int, int]] = set(zip(ys.tolist(), xs.tolist()))

    def nbrs8(y: int, x: int) -> list[tuple[int, int]]:
        return [
            (y + dy, x + dx)
            for dy in (-1, 0, 1)
            for dx in (-1, 0, 1)
            if (dy, dx) != (0, 0) and (y + dy, x + dx) in pt_set
        ]

    nc = {p: len(nbrs8(*p)) for p in pt_set}

    # Endpoints first (nc == 1), then the rest; guarantees complete strokes
    ordered = sorted(pt_set, key=lambda p: (nc[p] > 1, p))

    visited: set[tuple[int, int]] = set()
    paths: list[list[tuple[float, float]]] = []

    for start in ordered:
        if start in visited:
            continue
        path = [start]
        visited.add(start)
        prev: tuple[int, int] | None = None
        cur = start

        while True:
            cands = [n for n in nbrs8(*cur) if n not in visited]
            if not cands:
                break
            if prev is not None:
                dy, dx = cur[0] - prev[0], cur[1] - prev[1]
                straight = (cur[0] + dy, cur[1] + dx)
                nxt = straight if straight in set(cands) else cands[0]
            else:
                nxt = cands[0]
            prev, cur = cur, nxt
            visited.add(nxt)
            path.append(nxt)

        if len(path) >= 2:
            # Convert (row, col) → (x, y)
            paths.append([(float(col), float(row)) for row, col in path])

    # Any isolated dots
    for row, col in pt_set:
        if (row, col) not in visited:
            paths.append([(float(col), float(row))])

    return paths


def _smooth_path(
    path: list[tuple[float, float]], window: int = 5
) -> list[tuple[float, float]]:
    """Moving-average smoothing to remove pixel-grid jagginess."""
    n = len(path)
    if n < window:
        return path
    half = window // 2
    out = []
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        xs = [path[j][0] for j in range(lo, hi)]
        ys = [path[j][1] for j in range(lo, hi)]
        out.append((sum(xs) / len(xs), sum(ys) / len(ys)))
    return out


# ── Main synthesizer ──────────────────────────────────────────────────────────


class HandwritingSynthesizer:
    """
    Converts plain text to handwriting stroke coordinates.

    Rather than tracing glyph outlines (which produces "bubble-letter" strokes),
    this synthesizer:
      1. Rasterizes each glyph to a binary bitmap using PIL.
      2. Applies Zhang-Suen thinning to extract the 1-px centerline skeleton.
      3. Traces the skeleton into ordered stroke paths.
      4. Caches the result per glyph so the cost is paid only once per character.

    The result looks like actual pen strokes rather than outlines of filled shapes.
    """

    def __init__(self):
        self._font: TTFont | None = None
        self._glyph_set = None
        self._cmap: dict | None = None
        self._scale: float = 1.0
        self._cap_height_units: int = 700
        # Cache: glyph_name → list of paths in font-unit coordinates (y-up, baseline=0)
        self._skeleton_cache: dict[str, list[list[tuple[float, float]]]] = {}

    # ── Font loading ──────────────────────────────────────────────────────────

    def _ensure_font(self) -> None:
        if self._font is not None:
            return

        if not _FONT_PATH.exists():
            print("Downloading PatrickHand-Regular.ttf from Google Fonts…", flush=True)
            try:
                try:
                    import certifi
                    ctx = ssl.create_default_context(cafile=certifi.where())
                except ImportError:
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE

                with urllib.request.urlopen(_FONT_URL, context=ctx) as resp:
                    _FONT_PATH.write_bytes(resp.read())
                print("Font downloaded successfully.", flush=True)
            except Exception as e:
                raise RuntimeError(f"Could not download Patrick Hand font: {e}") from e

        self._font = TTFont(str(_FONT_PATH))
        self._glyph_set = self._font.getGlyphSet()
        self._cmap = self._font.getBestCmap() or {}

        upm = self._font["head"].unitsPerEm
        os2 = self._font.get("OS/2")
        if os2 and getattr(os2, "sCapHeight", 0):
            self._cap_height_units = os2.sCapHeight
        else:
            self._cap_height_units = int(upm * 0.7)

        self._scale = _TARGET_CAP_HEIGHT_PX / self._cap_height_units

    # ── Glyph skeleton (cached) ───────────────────────────────────────────────

    def _get_glyph_skeleton(
        self, glyph_name: str
    ) -> list[list[tuple[float, float]]]:
        """
        Return skeleton stroke paths for *glyph_name* in font-unit coordinates
        (x right, y up, baseline at y=0).  Computed once and cached.
        """
        if glyph_name in self._skeleton_cache:
            return self._skeleton_cache[glyph_name]

        glyph = self._glyph_set[glyph_name]
        pen = RecordingPen()
        glyph.draw(pen)
        contours = _recording_to_contours(pen.value)

        if not contours:
            self._skeleton_cache[glyph_name] = []
            return []

        # pixels-per-font-unit in the raster image
        rs = self._scale * _OVERSAMPLE
        PAD = 4

        # Allocate enough vertical space for ascenders and descenders
        asc_px  = int(self._cap_height_units * rs * 1.3) + PAD
        desc_px = int(self._cap_height_units * rs * 0.45) + PAD
        adv = glyph.width if hasattr(glyph, "width") else self._cap_height_units
        w_px = max(8, int(adv * rs) + PAD * 2)
        h_px = asc_px + desc_px
        baseline_px = asc_px  # row index where font y=0 maps to

        img = Image.new("L", (w_px, h_px), 0)
        draw = ImageDraw.Draw(img)

        for contour in contours:
            if len(contour) < 3:
                continue
            pts = [
                (int(round(PAD + fx * rs)), int(round(baseline_px - fy * rs)))
                for fx, fy in contour
            ]
            # TrueType (TTF) fonts use clockwise outer contours → negative signed area.
            # Inner counters/holes are counter-clockwise → positive signed area.
            # Fill outer contours white (255) and punch holes black (0).
            area = _signed_area(contour)
            draw.polygon(pts, fill=255 if area < 0 else 0)

        arr = np.array(img) > 127
        if not arr.any():
            self._skeleton_cache[glyph_name] = []
            return []

        skel = _zhang_suen_thin(arr)
        pixel_paths = _trace_skeleton(skel)

        font_paths: list[list[tuple[float, float]]] = []
        for pp in pixel_paths:
            if len(pp) < 2:
                continue
            # Convert pixel coords → font units (y-up)
            fp: list[tuple[float, float]] = [
                ((bx - PAD) / rs, (baseline_px - by) / rs)
                for bx, by in pp
            ]
            fp = _smooth_path(fp, window=5)
            if len(fp) >= 2:
                font_paths.append(fp)

        self._skeleton_cache[glyph_name] = font_paths
        return font_paths

    # ── Public API ────────────────────────────────────────────────────────────

    def synthesize(
        self,
        text: str,
        color: str = "#000000",
        position: dict | None = None,
    ) -> StrokeData:
        pos = position or {"x": 100, "y": 100}
        try:
            self._ensure_font()
            return self._synthesize_with_font(text, color, pos)
        except Exception as exc:
            print(f"Handwriting synthesis failed ({exc}); using stub.", flush=True)
            return self._stub(text, color, pos)

    # ── Font-based path ───────────────────────────────────────────────────────

    def _synthesize_with_font(self, text: str, color: str, position: dict) -> StrokeData:
        scale = self._scale
        strokes: list[Stroke] = []
        x_cursor = 0.0
        superscript_scale = scale * 0.62
        superscript_rise = _TARGET_CAP_HEIGHT_PX * 0.55
        drawn_char_count = 0

        def draw_char(char: str, char_scale: float, y_offset_px: float = 0.0) -> float:
            nonlocal drawn_char_count

            if char == " ":
                return self._cap_height_units * 0.32 * char_scale

            glyph_name = self._cmap.get(ord(char)) if self._cmap else None  # type: ignore[union-attr]
            if glyph_name is None or glyph_name not in self._glyph_set:
                return self._cap_height_units * 0.35 * char_scale

            try:
                glyph = self._glyph_set[glyph_name]
                advance_units = glyph.width if hasattr(glyph, "width") else self._cap_height_units * 0.5
                font_paths = self._get_glyph_skeleton(glyph_name)
            except Exception as exc:
                print(f"Glyph skeleton failed for {char!r}: {exc}", flush=True)
                return self._cap_height_units * 0.35 * char_scale

            # Stroke width: slightly thicker than the raw 1-px skeleton to look like pen ink.
            # Scale proportionally for superscripts.
            scale_ratio = char_scale / max(scale, 1e-9)
            stroke_width = round(2.2 * scale_ratio**0.9, 2)

            for fp in font_paths:
                if len(fp) < 2:
                    continue
                points: list[StrokePoint] = []
                n = len(fp)

                for idx, (fx, fy) in enumerate(fp):
                    cx = position["x"] + x_cursor + fx * char_scale
                    cy = position["y"] - fy * char_scale - y_offset_px

                    # Sine pressure curve: softer at stroke start/end, full in middle
                    t = idx / max(n - 1, 1)
                    pressure = 0.35 + 0.65 * math.sin(math.pi * t)

                    # Light pen-jitter proportional to scale
                    jitter = 0.4 * scale_ratio
                    cx += random.uniform(-jitter, jitter)
                    cy += random.uniform(-jitter, jitter)

                    points.append(
                        StrokePoint(
                            x=round(cx, 2),
                            y=round(cy, 2),
                            pressure=round(pressure, 3),
                        )
                    )

                strokes.append(Stroke(points=points, color=color, width=stroke_width))

            drawn_char_count += 1
            return advance_units * char_scale

        def read_superscript_token(src: str, start_idx: int) -> tuple[str, int]:
            if start_idx >= len(src):
                return "", 0
            opener = src[start_idx]
            if opener in "{(":
                closer = "}" if opener == "{" else ")"
                depth = 1
                j = start_idx + 1
                buf: list[str] = []
                while j < len(src):
                    ch = src[j]
                    if ch == opener:
                        depth += 1
                    elif ch == closer:
                        depth -= 1
                        if depth == 0:
                            return "".join(buf), (j - start_idx + 1)
                    if depth >= 1:
                        buf.append(ch)
                    j += 1
                return "".join(buf), (len(src) - start_idx)
            return src[start_idx], 1

        i = 0
        while i < len(text):
            char = text[i]
            if char == "\n":
                i += 1
                continue

            if char == "^":
                token, consumed = read_superscript_token(text, i + 1)
                if consumed > 0 and token:
                    for sup_char in token:
                        if sup_char in "\n{}()":
                            continue
                        x_cursor += draw_char(
                            sup_char,
                            char_scale=superscript_scale,
                            y_offset_px=superscript_rise,
                        )
                    i += consumed + 1
                    continue
                i += 1
                continue

            x_cursor += draw_char(char, char_scale=scale)
            i += 1

        total_pts = sum(len(s.points) for s in strokes)
        target_sec = max(1.0, 0.12 * max(drawn_char_count, 1))
        anim_speed = max(1.0, round(total_pts / (target_sec * 60 * 2), 2))

        return StrokeData(strokes=strokes, position=position, animation_speed=anim_speed)

    # ── Stub fallback ─────────────────────────────────────────────────────────

    def _stub(self, text: str, color: str, position: dict) -> StrokeData:
        """Simple per-character diagonal line — used when the font is unavailable."""
        stub_strokes: list[Stroke] = []
        x_off = 0.0
        for char in text:
            if char == " ":
                x_off += 10
                continue
            stub_strokes.append(
                Stroke(
                    points=[
                        StrokePoint(x=position["x"] + x_off, y=position["y"]),
                        StrokePoint(x=position["x"] + x_off + 8, y=position["y"] + 12),
                    ],
                    color=color,
                    width=2.0,
                )
            )
            x_off += 12
        return StrokeData(strokes=stub_strokes, position=position, animation_speed=1.0)
