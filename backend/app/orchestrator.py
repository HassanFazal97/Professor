import asyncio
import base64
import time

from fastapi import WebSocket

from app.handwriting.synthesizer import HandwritingSynthesizer
from app.llm_client import LLMClient
from app.session import TutorSession
from app.stt_client import STTClient
from app.tts_client import TTSClient


class Orchestrator:
    """Routes incoming WebSocket messages to the appropriate subsystem."""

    def __init__(self, session: TutorSession, websocket: WebSocket):
        self.session = session
        self.websocket = websocket
        self.llm = LLMClient()
        self.tts = TTSClient()
        self.stt = STTClient()
        self.handwriting = HandwritingSynthesizer()

        # STT state — set up when audio_start is received
        self._audio_queue: asyncio.Queue | None = None
        self._stt_task: asyncio.Task | None = None

        # Echo cooldown: ignore transcripts for this many seconds after Ada's
        # audio is sent, to prevent Ada's own TTS voice from being re-processed.
        self._last_tts_sent_at: float = 0.0
        self._echo_cooldown: float = 1.5

    async def on_connect(self) -> None:
        await self.websocket.send_json(
            {
                "type": "connected",
                "session_id": self.session.session_id,
                "message": "Connected to AI Tutor. Say hello to Professor Ada!",
            }
        )

    async def handle_message(self, data: dict) -> None:
        msg_type = data.get("type")

        if msg_type == "session_start":
            await self._handle_session_start(data)
        elif msg_type == "transcript":
            await self._handle_transcript(data)
        elif msg_type == "board_snapshot":
            await self._handle_board_snapshot(data)
        elif msg_type == "audio_start":
            await self._handle_audio_start()
        elif msg_type == "audio_data":
            await self._handle_audio_data(data)
        elif msg_type == "audio_stop":
            await self._handle_audio_stop()
        else:
            await self.websocket.send_json(
                {"type": "error", "message": f"Unknown message type: {msg_type}"}
            )

    # ── Session / LLM ────────────────────────────────────────────────────────

    async def _handle_session_start(self, data: dict) -> None:
        self.session.current_subject = data.get("subject", "")
        self.session.is_active = True
        self.session.tutor_mode = "listening"

        subject_label = self.session.current_subject or "whatever I need"
        self.session.add_user_turn(
            f"Hey, let's work on {subject_label}.",
            time.time(),
        )

        tts_task: asyncio.Task | None = None

        async def on_speech_ready(text: str) -> None:
            nonlocal tts_task
            self.session.add_assistant_turn(text, time.time())
            await self.websocket.send_json({"type": "speech_text", "text": text})
            tts_task = asyncio.create_task(self.tts.synthesize(text))

        llm_response = await self.llm.get_response(
            self.session.to_anthropic_messages(),
            on_speech_ready=on_speech_ready,
        )
        await self._dispatch_llm_response(llm_response, tts_task)

    async def _handle_transcript(self, data: dict) -> None:
        text = data.get("text", "").strip()
        if not text:
            return

        self.session.add_user_turn(text, time.time())

        latest_snapshot = (
            self.session.board_snapshots[-1].image_base64
            if self.session.board_snapshots
            else None
        )

        tts_task: asyncio.Task | None = None

        async def on_speech_ready(text: str) -> None:
            nonlocal tts_task
            self.session.add_assistant_turn(text, time.time())
            await self.websocket.send_json({"type": "speech_text", "text": text})
            tts_task = asyncio.create_task(self.tts.synthesize(text))

        llm_response = await self.llm.get_response(
            self.session.to_anthropic_messages(),
            board_snapshot_b64=latest_snapshot,
            on_speech_ready=on_speech_ready,
        )
        await self._dispatch_llm_response(llm_response, tts_task)

    async def _handle_board_snapshot(self, data: dict) -> None:
        image_b64 = data.get("image_base64", "")
        if not image_b64:
            return
        self.session.add_board_snapshot(image_b64, time.time())
        await self.websocket.send_json(
            {"type": "snapshot_received", "count": len(self.session.board_snapshots)}
        )

    # ── STT / Audio ──────────────────────────────────────────────────────────

    async def _handle_audio_start(self) -> None:
        """Open a Deepgram session as a background task."""
        if self._stt_task and not self._stt_task.done():
            self._stt_task.cancel()

        self._audio_queue = asyncio.Queue()
        self._stt_task = asyncio.create_task(
            self.stt.stream_session(
                self._audio_queue,
                self._on_stt_transcript,
                self._on_speech_start,
            )
        )

    async def _handle_audio_data(self, data: dict) -> None:
        """Decode base64 audio chunk and push into the STT queue."""
        if self._audio_queue is None:
            return
        b64 = data.get("data", "")
        if b64:
            audio_bytes = base64.b64decode(b64)
            await self._audio_queue.put(audio_bytes)

    async def _handle_audio_stop(self) -> None:
        """Signal end-of-stream to Deepgram."""
        if self._audio_queue is not None:
            await self._audio_queue.put(None)  # sentinel
            self._audio_queue = None

    async def _on_speech_start(self) -> None:
        """
        Deepgram detected the start of speech (fires before the transcript is ready).
        Tell the frontend to cut Ada's audio immediately — barge-in.
        Also reset the echo cooldown so the upcoming transcript is not suppressed.
        """
        self._last_tts_sent_at = 0.0  # reset cooldown so barge-in transcript is processed
        await self.websocket.send_json({"type": "barge_in"})

    async def _on_stt_transcript(self, text: str) -> None:
        """
        Called by STTClient when a final transcript arrives from Deepgram.
        Skips transcripts that arrive too soon after Ada's TTS (likely echo).
        """
        import time as _time
        elapsed = _time.time() - self._last_tts_sent_at
        if elapsed < self._echo_cooldown:
            print(f"STT echo suppressed ({elapsed:.2f}s after TTS): {text!r}")
            return

        await self.websocket.send_json({"type": "transcript_interim", "text": text})
        await self._handle_transcript({"text": text})

    # ── LLM response dispatch ────────────────────────────────────────────────

    async def _dispatch_llm_response(
        self,
        llm_response: dict,
        tts_task: asyncio.Task | None = None,
    ) -> None:
        """
        Send board actions to the frontend, then await TTS audio and send it.

        tts_task is an already-running asyncio.Task started by on_speech_ready
        the moment the speech field was parsed from the stream. By the time we
        reach the audio step here, TTS has had a head-start overlapping with
        board-action processing — cutting perceived latency significantly.
        """
        speech = llm_response.get("speech", "")
        board_actions = llm_response.get("board_actions", [])
        tutor_state = llm_response.get("tutor_state", "listening")

        self.session.tutor_mode = tutor_state

        # speech_text + assistant turn already handled in on_speech_ready;
        # only do it here as fallback if streaming didn't fire (e.g. empty speech).
        if speech and tts_task is None:
            self.session.add_assistant_turn(speech, time.time())
            await self.websocket.send_json({"type": "speech_text", "text": speech})
            tts_task = asyncio.create_task(self.tts.synthesize(speech))

        # Process board actions — TTS is running in parallel as a background task.
        print(f"[Orchestrator] Processing {len(board_actions)} board_action(s)")
        for action in board_actions:
            if action.get("type") == "write":
                # Haiku sometimes returns content as a non-string or position
                # as a non-dict — coerce both defensively.
                raw_content = action.get("content", "")
                text_content = raw_content if isinstance(raw_content, str) else str(raw_content)

                raw_pos = action.get("position", {})
                if isinstance(raw_pos, dict):
                    position = {
                        "x": float(raw_pos.get("x", 100)),
                        "y": float(raw_pos.get("y", 100)),
                    }
                else:
                    position = {"x": 100, "y": 100}

                stroke_data = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda t=text_content, c=action.get("color", "#000000"), p=position: (
                        self.handwriting.synthesize(text=t, color=c, position=p)
                    ),
                )
                await self.websocket.send_json(
                    {"type": "strokes", "strokes": stroke_data.to_dict()}
                )
            else:
                await self.websocket.send_json({"type": "board_action", "action": action})

        # Await TTS (usually already done by the time we get here).
        if tts_task is not None:
            audio_bytes = await tts_task
            if audio_bytes:
                audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
                await self.websocket.send_json({"type": "audio_chunk", "data": audio_b64})
                self._last_tts_sent_at = time.time()
