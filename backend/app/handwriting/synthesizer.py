from dataclasses import dataclass


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


class HandwritingSynthesizer:
    """
    Converts plain text to handwriting stroke coordinates.

    Uses the sjvasquez/handwriting-synthesis model which outputs
    (x, y, end_of_stroke) tuples that we convert to our StrokeData format.
    """

    def __init__(self):
        # TODO: load the handwriting-synthesis TensorFlow model
        # Model checkpoint lives at handwriting/checkpoints/
        self.model = None
        self._model_loaded = False

    def synthesize(
        self,
        text: str,
        color: str = "#000000",
        position: dict | None = None,
    ) -> StrokeData:
        """
        Convert text to stroke data.

        Args:
            text: The text to render as handwriting
            color: Hex color string for the strokes
            position: {"x": float, "y": float} top-left origin on the whiteboard

        Returns:
            StrokeData ready to serialize and send to the frontend
        """
        # TODO: replace stub with real model inference
        # 1. Tokenize text
        # 2. Run through handwriting-synthesis LSTM
        # 3. Convert (x, y, eos) tuples to absolute coordinates
        # 4. Apply ±1px jitter for organic feel
        # 5. Wrap in StrokeData

        position = position or {"x": 100, "y": 100}

        # Stub: return a simple horizontal line per character
        stub_strokes = []
        x_offset = 0.0
        for char in text:
            if char == " ":
                x_offset += 10
                continue
            stub_strokes.append(
                Stroke(
                    points=[
                        StrokePoint(x=position["x"] + x_offset, y=position["y"]),
                        StrokePoint(x=position["x"] + x_offset + 8, y=position["y"] + 12),
                    ],
                    color=color,
                    width=2.0,
                )
            )
            x_offset += 12

        return StrokeData(
            strokes=stub_strokes,
            position=position,
            animation_speed=1.0,
        )
