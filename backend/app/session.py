from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from app.models import TutorSessionRecord

TutorMode = Literal["listening", "guiding", "demonstrating", "evaluating"]


@dataclass
class BoardSnapshot:
    image_base64: str
    timestamp: float
    description: str = ""


@dataclass
class ConversationTurn:
    role: Literal["user", "assistant"]
    content: str
    timestamp: float = 0.0


@dataclass
class TutorSession:
    session_id: str
    conversation_history: list[ConversationTurn] = field(default_factory=list)
    current_subject: str = ""
    tutor_mode: TutorMode = "listening"
    board_snapshots: list[BoardSnapshot] = field(default_factory=list)
    student_progress: dict = field(default_factory=dict)
    is_active: bool = False

    # Tracks how far down the canvas Ada has written so the orchestrator
    # knows where free space starts. 0 means the board is blank.
    # All y-values are in world (page) coordinates.
    board_next_y: int = 0          # world y of Ada's writing cursor
    board_viewport_y: int = 0      # world y of top of current visible viewport
    student_content_bottom_y: int = 0  # world y of bottommost student content
    board_width: int = 1200
    board_height: int = 700

    def get_board_state_context(self) -> str:
        """
        Return a short note for the LLM describing the current whiteboard state.
        Vertical placement is handled automatically by the orchestrator —
        Ada always uses y=140 as her starting y.
        """
        if self.board_next_y == 0 and self.board_viewport_y == 0:
            return ""
        # Convert world cursor to viewport-relative position for space calculation.
        effective_y = max(0, self.board_next_y - self.board_viewport_y)
        if effective_y == 0:
            return ""
        space_left = self.board_height - effective_y
        if space_left < 150:
            return (
                "[Whiteboard: nearly full — board will auto-scroll on your next write. "
                "Write at your normal starting position x=80, y=140.]"
            )
        return (
            "[Whiteboard: has existing content. Your writing will be placed below it "
            "automatically — always use x=80, y=140 as your starting position.]"
        )

    def add_user_turn(self, text: str, timestamp: float = 0.0) -> None:
        self.conversation_history.append(
            ConversationTurn(role="user", content=text, timestamp=timestamp)
        )

    def add_assistant_turn(self, text: str, timestamp: float = 0.0) -> None:
        self.conversation_history.append(
            ConversationTurn(role="assistant", content=text, timestamp=timestamp)
        )

    def add_board_snapshot(self, image_base64: str, timestamp: float) -> None:
        snapshot = BoardSnapshot(image_base64=image_base64, timestamp=timestamp)
        self.board_snapshots.append(snapshot)
        # Keep only the last 10 snapshots to limit memory
        if len(self.board_snapshots) > 10:
            self.board_snapshots = self.board_snapshots[-10:]

    @classmethod
    def from_db_record(cls, record: "TutorSessionRecord", page_id: str) -> "TutorSession":
        """Reconstruct a TutorSession from a persisted DB record."""
        history = []
        for turn in (record.conversation_history or []):
            history.append(
                ConversationTurn(
                    role=turn["role"],
                    content=turn["content"],
                    timestamp=turn.get("timestamp", 0.0),
                )
            )
        return cls(
            session_id=page_id,
            conversation_history=history,
            current_subject=record.current_subject or "",
            tutor_mode=record.tutor_mode or "listening",
            board_next_y=record.board_next_y,
            board_viewport_y=record.board_viewport_y,
            student_content_bottom_y=record.student_content_bottom_y,
            board_width=record.board_width,
            board_height=record.board_height,
            is_active=True,
        )

    def to_db_dict(self) -> dict:
        """Serialize session scalars for upsert into tutor_sessions."""
        return {
            "current_subject": self.current_subject,
            "tutor_mode": self.tutor_mode,
            "board_next_y": self.board_next_y,
            "board_viewport_y": self.board_viewport_y,
            "student_content_bottom_y": self.student_content_bottom_y,
            "board_width": self.board_width,
            "board_height": self.board_height,
            "conversation_history": [
                {
                    "role": t.role,
                    "content": t.content,
                    "timestamp": t.timestamp,
                }
                for t in self.conversation_history
            ],
        }

    def to_anthropic_messages(self) -> list[dict]:
        """Convert conversation history to Anthropic API message format."""
        messages = []
        for turn in self.conversation_history:
            messages.append({"role": turn.role, "content": turn.content})
        return messages
