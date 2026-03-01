import math
import os
import re
import xml.etree.ElementTree as ET
from typing import Any

import aiohttp
from svgpathtools import parse_path

from app.handwriting.synthesizer import HandwritingSynthesizer, Stroke, StrokeData, StrokePoint


class LaTeXToStrokes:
    """
    Converts LaTeX math expressions to stroke coordinates.

    Pipeline:
      LaTeX → MathJax server-side SVG → extract <path d="..."> → sample points → StrokeData
    """

    def __init__(self):
        self.mathjax_url = os.getenv("LATEX_RENDER_URL", "http://localhost:3001/mathjax")
        self._fallback_writer = HandwritingSynthesizer()
        # Base/limits for adaptive LaTeX sizing to match nearby handwriting.
        self._target_height_px = float(os.getenv("LATEX_TARGET_HEIGHT_PX", "34"))
        self._target_height_min_px = float(os.getenv("LATEX_TARGET_HEIGHT_MIN_PX", "28"))
        self._target_height_max_px = float(os.getenv("LATEX_TARGET_HEIGHT_MAX_PX", "44"))

    async def convert(
        self,
        latex: str,
        color: str = "#000000",
        position: dict | None = None,
        max_width_px: float | None = None,
    ) -> StrokeData:
        """
        Convert a LaTeX string to stroke data.

        Args:
            latex: LaTeX expression e.g. r"\\frac{1}{2}"
            color: Hex color for strokes
            position: {"x": float, "y": float} top-left origin

        Returns:
            StrokeData with sampled path points
        """
        position = position or {"x": 100, "y": 100}
        svg = await self._render_svg(latex)
        if not svg:
            return self._fallback(latex, color, position)

        strokes = self._svg_to_strokes(
            svg,
            color,
            position,
            latex=latex,
            max_width_px=max_width_px,
        )
        if not strokes:
            return self._fallback(latex, color, position)

        return StrokeData(strokes=strokes, position=position, animation_speed=1.0)

    async def _render_svg(self, latex: str) -> str:
        payload = {
            "latex": latex,
            "display": True,
        }

        timeout = aiohttp.ClientTimeout(total=8)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.mathjax_url, json=payload) as resp:
                    resp.raise_for_status()
                    ctype = (resp.headers.get("Content-Type") or "").lower()
                    if "application/json" in ctype:
                        data: Any = await resp.json()
                        if isinstance(data, dict):
                            svg = data.get("svg")
                            if isinstance(svg, str):
                                return svg
                    return await resp.text()
        except Exception as exc:
            print(f"[LaTeX] MathJax render failed: {exc}")
            return ""

    def _svg_to_strokes(
        self,
        svg_text: str,
        color: str,
        position: dict,
        latex: str = "",
        max_width_px: float | None = None,
    ) -> list[Stroke]:
        try:
            root = ET.fromstring(svg_text)
        except Exception as exc:
            print(f"[LaTeX] SVG parse failed: {exc}")
            return []

        path_entries: list[tuple[str, tuple[float, float, float, float, float, float]]] = []

        def walk(node: ET.Element, transform: tuple[float, float, float, float, float, float]) -> None:
            node_transform = self._parse_transform(node.attrib.get("transform", ""))
            current = self._mul_affine(transform, node_transform)

            if self._strip_ns(node.tag) == "path":
                d = node.attrib.get("d", "")
                if d:
                    path_entries.append((d, current))

            for child in list(node):
                walk(child, current)

        walk(root, (1.0, 0.0, 0.0, 1.0, 0.0, 0.0))
        if not path_entries:
            return []

        sampled: list[list[tuple[float, float]]] = []
        min_x = float("inf")
        min_y = float("inf")
        max_x = float("-inf")
        max_y = float("-inf")

        for d, affine in path_entries:
            pts = self._sample_svg_path(d)
            if len(pts) < 2:
                continue

            transformed = [self._apply_affine(x, y, affine) for x, y in pts]
            for x, y in transformed:
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)
            sampled.append(transformed)

        if (
            not sampled
            or not math.isfinite(min_x)
            or not math.isfinite(min_y)
            or not math.isfinite(max_x)
            or not math.isfinite(max_y)
        ):
            return []

        src_w = max(1.0, max_x - min_x)
        src_h = max(1.0, max_y - min_y)

        # Primary normalization: adaptive equation height based on expression complexity.
        target_height = self._estimate_target_height(latex)
        scale = target_height / src_h

        # Secondary clamp: keep long equations within available board width.
        if max_width_px is not None and max_width_px > 40:
            scaled_w = src_w * scale
            if scaled_w > max_width_px:
                scale *= max_width_px / scaled_w

        off_x = float(position.get("x", 100))
        off_y = float(position.get("y", 100))

        strokes: list[Stroke] = []
        for contour in sampled:
            points = [
                StrokePoint(
                    x=off_x + (x - min_x) * scale,
                    y=off_y + (y - min_y) * scale,
                    pressure=0.75,
                )
                for x, y in contour
            ]
            if len(points) >= 2:
                strokes.append(Stroke(points=points, color=color, width=2.0))

        return strokes

    def _estimate_target_height(self, latex: str) -> float:
        """
        Heuristic sizing:
        - Keep simple inline expressions compact
        - Expand complex structures (fractions, roots, integrals, sums, matrices)
          so they remain legible without user zoom.
        """
        text = latex or ""
        complexity = 0

        # Structural commands with higher visual density.
        weighted_tokens = [
            (r"\\frac", 2.0),
            (r"\\dfrac", 2.0),
            (r"\\tfrac", 1.5),
            (r"\\sqrt", 1.4),
            (r"\\int", 1.8),
            (r"\\sum", 1.8),
            (r"\\prod", 1.8),
            (r"\\lim", 1.2),
            (r"\\begin\{matrix\}", 2.4),
            (r"\\begin\{pmatrix\}", 2.4),
            (r"\\begin\{bmatrix\}", 2.4),
            (r"\\left", 1.0),
            (r"\\right", 1.0),
        ]
        for pattern, weight in weighted_tokens:
            complexity += len(re.findall(pattern, text)) * weight

        # Penalize deep superscript/subscript usage.
        complexity += text.count("^") * 0.45
        complexity += text.count("_") * 0.45

        # Very long expressions get a small readability bump.
        complexity += min(2.0, max(0.0, (len(text) - 24) / 40.0))

        # Map complexity -> target height.
        # Typical range ends up ~28px (simple) to ~44px (complex).
        height = self._target_height_px + complexity * 2.2 - 4.0
        return min(self._target_height_max_px, max(self._target_height_min_px, height))

    def _sample_svg_path(self, path_d: str) -> list[tuple[float, float]]:
        """Sample evenly-spaced points along an SVG path string."""
        try:
            path = parse_path(path_d)
        except Exception:
            return []

        total_len = path.length(error=1e-4)
        num_points = max(12, min(220, int(total_len / 3.0)))
        points: list[tuple[float, float]] = []
        for i in range(num_points + 1):
            t = i / num_points
            pt = path.point(t)
            points.append((float(pt.real), float(pt.imag)))
        return points

    def _fallback(self, latex: str, color: str, position: dict) -> StrokeData:
        plain = self._latex_to_plain(latex)
        return self._fallback_writer.synthesize(plain, color=color, position=position)

    def _latex_to_plain(self, text: str) -> str:
        out = text.strip()
        out = re.sub(r"\\frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}", r"(\1)/(\2)", out)
        out = re.sub(r"\\sqrt\s*\{([^{}]+)\}", r"sqrt(\1)", out)
        out = re.sub(r"\\([a-zA-Z]+)", r"\1", out)
        out = out.replace("{", "(").replace("}", ")")
        out = out.replace("^", " ^ ").replace("_", " _ ")
        out = re.sub(r"\s+", " ", out).strip()
        return out or "math"

    def _strip_ns(self, tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    def _parse_transform(self, transform: str) -> tuple[float, float, float, float, float, float]:
        if not transform.strip():
            return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

        current = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
        for fn, arg_str in re.findall(r"([a-zA-Z]+)\(([^)]*)\)", transform):
            nums = [
                float(x)
                for x in re.split(r"[,\s]+", arg_str.strip())
                if x.strip()
            ]
            if fn == "matrix" and len(nums) == 6:
                m = tuple(nums)  # type: ignore[assignment]
            elif fn == "translate":
                tx = nums[0] if len(nums) >= 1 else 0.0
                ty = nums[1] if len(nums) >= 2 else 0.0
                m = (1.0, 0.0, 0.0, 1.0, tx, ty)
            elif fn == "scale":
                sx = nums[0] if len(nums) >= 1 else 1.0
                sy = nums[1] if len(nums) >= 2 else sx
                m = (sx, 0.0, 0.0, sy, 0.0, 0.0)
            else:
                continue
            current = self._mul_affine(current, m)
        return current

    def _mul_affine(
        self,
        a: tuple[float, float, float, float, float, float],
        b: tuple[float, float, float, float, float, float],
    ) -> tuple[float, float, float, float, float, float]:
        a0, a1, a2, a3, a4, a5 = a
        b0, b1, b2, b3, b4, b5 = b
        return (
            a0 * b0 + a2 * b1,
            a1 * b0 + a3 * b1,
            a0 * b2 + a2 * b3,
            a1 * b2 + a3 * b3,
            a0 * b4 + a2 * b5 + a4,
            a1 * b4 + a3 * b5 + a5,
        )

    def _apply_affine(
        self,
        x: float,
        y: float,
        t: tuple[float, float, float, float, float, float],
    ) -> tuple[float, float]:
        a, b, c, d, e, f = t
        return (a * x + c * y + e, b * x + d * y + f)
