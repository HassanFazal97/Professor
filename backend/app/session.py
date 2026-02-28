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
