import math
import random
import ssl
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTFont

# Patrick Hand is a Google Font (OFL license) designed to look like clean,
# printed handwriting — less curvy/cursive than Caveat.
# We download the static TTF on first use and cache it next to this file.
_FONT_URL = (
    "https://cdn.jsdelivr.net/gh/google/fonts@main"
    "/ofl/patrickhand/PatrickHand-Regular.ttf"
)
_FONT_PATH = Path(__file__).parent / "PatrickHand-Regular.ttf"

# How tall capital letters should appear on the whiteboard canvas (px).
_TARGET_CAP_HEIGHT_PX = 40


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
    """Sample n+1 points on a quadratic bezier p0→p2 with control p1."""
    pts = []
    for i in range(n + 1):
        t = i / n
        mt = 1 - t
        x = mt * mt * p0[0] + 2 * mt * t * p1[0] + t * t * p2[0]
        y = mt * mt * p0[1] + 2 * mt * t * p1[1] + t * t * p2[1]
        pts.append((x, y))
    return pts


def _sample_cubic(p0, p1, p2, p3, n: int = 4) -> list[tuple]:
    """Sample n+1 points on a cubic bezier p0→p3 with controls p1, p2."""
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
    """
    Convert a RecordingPen's value list into a list of contours.
    Each contour is a list of (x, y) tuples in font units.
    Bezier curves are sampled into line segments.
    """
    contours: list[list[tuple]] = []
    current: list[tuple] = []

    for op, args in value:
        if op == "moveTo":
            # args = ((x, y),)
            if len(current) > 1:
                contours.append(current)
            current = [args[0]]

        elif op == "lineTo":
            # args = ((x, y),)
            current.append(args[0])

        elif op == "qCurveTo":
            # args = (off_curve_1, ..., on_curve_end)
            # TrueType quadratic spline: consecutive off-curves have an implicit
            # on-curve midpoint between them.
            pts = list(args)
            start = current[-1] if current else pts[0]

            while len(pts) > 2:
                p1 = pts[0]
                # Implicit on-curve midpoint between two consecutive off-curves
                p2 = (
                    (pts[0][0] + pts[1][0]) / 2.0,
                    (pts[0][1] + pts[1][1]) / 2.0,
                )
                current.extend(_sample_quadratic(start, p1, p2)[1:])
                start = p2
                pts.pop(0)

            # Final segment: start → pts[1] with control pts[0]
            if len(pts) == 2:
                current.extend(_sample_quadratic(start, pts[0], pts[1])[1:])
            elif len(pts) == 1:
                current.append(pts[0])

        elif op == "curveTo":
            # args = (cp1, cp2, end_point)  — cubic bezier
            p0 = current[-1] if current else args[0]
            current.extend(_sample_cubic(p0, args[0], args[1], args[2])[1:])

        elif op in ("closePath", "endPath"):
            if len(current) > 1:
                contours.append(current)
            current = []

    if len(current) > 1:
        contours.append(current)

    return contours


# ── Main synthesizer ──────────────────────────────────────────────────────────


class HandwritingSynthesizer:
    """
    Converts plain text to handwriting stroke coordinates using the
    Patrick Hand font (Google Fonts, OFL license) — a clean, printed
    handwriting style.

    The font is downloaded once to the package directory and cached.
    If the font or fonttools is unavailable, the stub path is used as fallback.
    """

    def __init__(self):
        self._font: TTFont | None = None
        self._glyph_set = None
        self._cmap: dict | None = None
        self._scale: float = 1.0
        self._cap_height_units: int = 700  # fallback

    # ── Font loading ──────────────────────────────────────────────────────────

    def _ensure_font(self) -> None:
        if self._font is not None:
            return

        if not _FONT_PATH.exists():
            print("Downloading PatrickHand-Regular.ttf from Google Fonts…", flush=True)
            try:
                # macOS Python often lacks system CA certs; try certifi first,
                # then fall back to an unverified context (font download only).
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
                raise RuntimeError(f"Could not download Caveat font: {e}") from e

        self._font = TTFont(str(_FONT_PATH))
        self._glyph_set = self._font.getGlyphSet()
        self._cmap = self._font.getBestCmap() or {}

        upm = self._font["head"].unitsPerEm

        # Prefer OS/2 sCapHeight; fall back to 70% of UPM
        os2 = self._font.get("OS/2")
        if os2 and getattr(os2, "sCapHeight", 0):
            self._cap_height_units = os2.sCapHeight
        else:
            self._cap_height_units = int(upm * 0.7)

        self._scale = _TARGET_CAP_HEIGHT_PX / self._cap_height_units

    # ── Public API ────────────────────────────────────────────────────────────

    def synthesize(
        self,
        text: str,
        color: str = "#000000",
        position: dict | None = None,
    ) -> StrokeData:
        """
        Convert *text* to stroke data ready to send to the frontend.

        Falls back to a simple stub if the font can't be loaded.
        """
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
        x_cursor = 0.0  # accumulated horizontal advance in scaled pixels
        superscript_scale = scale * 0.62
        superscript_rise = _TARGET_CAP_HEIGHT_PX * 0.55
        drawn_char_count = 0

        def draw_char(char: str, char_scale: float, y_offset_px: float = 0.0) -> float:
            """Draw a single character and return horizontal advance in px."""
            nonlocal drawn_char_count

            if char == " ":
                return self._cap_height_units * 0.32 * char_scale

            glyph_name = self._cmap.get(ord(char)) if self._cmap else None  # type: ignore[union-attr]

            if glyph_name is None or glyph_name not in self._glyph_set:
                # Use a space-width advance for unknown characters
                return self._cap_height_units * 0.35 * char_scale

            try:
                glyph = self._glyph_set[glyph_name]
                pen = RecordingPen()
                glyph.draw(pen)
                contours = _recording_to_contours(pen.value)
                advance_units = (
                    glyph.width if hasattr(glyph, "width") else self._cap_height_units * 0.5
                )
            except Exception as exc:
                print(f"Glyph render failed for {char!r}: {exc}", flush=True)
                return self._cap_height_units * 0.35 * char_scale

            for contour in contours:
                if len(contour) < 2:
                    continue

                points: list[StrokePoint] = []
                n = len(contour)

                for idx, pt in enumerate(contour):
                    try:
                        fx, fy = pt
                    except (TypeError, ValueError):
                        continue

                    # Transform to canvas coordinates:
                    # • X: position["x"] + current character offset + glyph x * char_scale
                    # • Y: font Y-axis is up; canvas Y-axis is down.
                    px = position["x"] + x_cursor + fx * char_scale
                    py = position["y"] - fy * char_scale - y_offset_px

                    # Sine pressure curve: soft at start and end, full in the middle
                    t = idx / max(n - 1, 1)
                    pressure = 0.4 + 0.6 * math.sin(math.pi * t)

                    # Keep jitter proportional when drawing smaller superscripts.
                    jitter = 0.8 * (char_scale / max(scale, 1e-6))
                    px += random.uniform(-jitter, jitter)
                    py += random.uniform(-jitter, jitter)

                    points.append(
                        StrokePoint(
                            x=round(px, 2),
                            y=round(py, 2),
                            pressure=round(pressure, 3),
                        )
                    )

                stroke_width = 1.5 * (char_scale / max(scale, 1e-6)) ** 0.85
                strokes.append(Stroke(points=points, color=color, width=round(stroke_width, 2)))

            drawn_char_count += 1
            return advance_units * char_scale

        def read_superscript_token(src: str, start_idx: int) -> tuple[str, int]:
            """
            Read exponent token after '^':
            - x^{n-1} -> "n-1"
            - x^(n-1) -> "n-1"
            - x^n -> "n"
            Returns (token_text, consumed_chars_from_start_idx).
            """
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
                # Unmatched group: consume until end, best-effort rendering.
                return "".join(buf), (len(src) - start_idx)

            return src[start_idx], 1

        i = 0
        while i < len(text):
            char = text[i]
            if char == "\n":
                i += 1
                continue  # multi-line layout not implemented

            # Render caret notation as true superscript in stroke coordinates.
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

        # Set animation speed so writing takes ~0.12s per character (min 1s total).
        # The frontend draws `Math.round(speed * 2)` points per frame at ~60fps.
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
