from dataclasses import dataclass, field
from typing import Literal

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

    # Tracks how far down the canvas Ada has written, so the LLM knows where
    # free space is.  Updated by the orchestrator after each set of write actions.
    # 0 means the board is blank (nothing written yet).
    board_next_y: int = 0
    board_next_x: int = 80
    board_width: int = 1200
    board_height: int = 700

    def get_board_state_context(self) -> str:
        """
        Return a short note for the LLM describing the current whiteboard state.
        Injected into the last user message before each LLM call so Ada knows
        the board status. Positioning is handled automatically by the orchestrator,
        so Ada does not need to calculate y-offsets herself.
        """
        if self.board_next_y == 0:
            return ""
        space_left = self.board_height - self.board_next_y
        if space_left < 150:
            return (
                "[Whiteboard: board is nearly full. "
                "It will auto-clear when you next draw — write at your normal starting positions.]"
            )
        return (
            f"[Whiteboard: has existing content. "
            f"Your board_actions will be placed below it automatically — "
            f"always use x=80, y=140 as your starting position as normal.]"
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

    def to_anthropic_messages(self) -> list[dict]:
        """Convert conversation history to Anthropic API message format."""
        messages = []
        for turn in self.conversation_history:
            messages.append({"role": turn.role, "content": turn.content})
        return messages
