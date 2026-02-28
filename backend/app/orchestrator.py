import time

from fastapi import WebSocket

from app.llm_client import LLMClient
from app.session import TutorSession
from app.tts_client import TTSClient


class Orchestrator:
    """Routes incoming WebSocket messages to the appropriate subsystem."""

    def __init__(self, session: TutorSession, websocket: WebSocket):
        self.session = session
        self.websocket = websocket
        self.llm = LLMClient()
        self.tts = TTSClient()

    async def on_connect(self) -> None:
        """Called when a client connects. Send a greeting."""
        await self.websocket.send_json(
            {
                "type": "connected",
                "session_id": self.session.session_id,
                "message": "Connected to AI Tutor. Say hello to Professor Ada!",
            }
        )

    async def handle_message(self, data: dict) -> None:
        """Dispatch incoming messages by type."""
        msg_type = data.get("type")

        if msg_type == "session_start":
            await self._handle_session_start(data)
        elif msg_type == "transcript":
            await self._handle_transcript(data)
        elif msg_type == "board_snapshot":
            await self._handle_board_snapshot(data)
        else:
            await self.websocket.send_json(
                {"type": "error", "message": f"Unknown message type: {msg_type}"}
            )

    async def _handle_session_start(self, data: dict) -> None:
        self.session.current_subject = data.get("subject", "")
        self.session.is_active = True
        self.session.tutor_mode = "listening"

        # TODO: Generate a greeting from the LLM
        greeting = (
            f"Hello! I'm Professor Ada. I'll be helping you with "
            f"{self.session.current_subject or 'your studies'} today. "
            "What would you like to work on?"
        )
        self.session.add_assistant_turn(greeting, time.time())

        await self.websocket.send_json({"type": "speech_text", "text": greeting})
        # TODO: stream TTS audio chunks

    async def _handle_transcript(self, data: dict) -> None:
        text = data.get("text", "").strip()
        if not text:
            return

        self.session.add_user_turn(text, time.time())

        # TODO: call LLM with conversation history + latest board snapshot
        # For now, echo a stub response
        response_text = f"[Stub] You said: {text}"
        self.session.add_assistant_turn(response_text, time.time())

        await self.websocket.send_json({"type": "speech_text", "text": response_text})

    async def _handle_board_snapshot(self, data: dict) -> None:
        image_b64 = data.get("image_base64", "")
        if not image_b64:
            return

        self.session.add_board_snapshot(image_b64, time.time())
        await self.websocket.send_json(
            {"type": "snapshot_received", "count": len(self.session.board_snapshots)}
        )
