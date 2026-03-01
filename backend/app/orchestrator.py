import asyncio
import base64
import os
import time
import textwrap

from fastapi import WebSocket

from app.handwriting.latex_to_strokes import LaTeXToStrokes
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
        self.latex = LaTeXToStrokes()

        # STT state — set up when audio_start is received
        self._audio_queue: asyncio.Queue | None = None
        self._stt_task: asyncio.Task | None = None

        # Echo cooldown: ignore transcripts for this many seconds after Ada's
        # audio is sent, to prevent Ada's own TTS voice from being re-processed.
        self._last_tts_sent_at: float = 0.0
        self._last_tts_started_at: float = 0.0
        self._echo_cooldown: float = float(os.getenv("ECHO_COOLDOWN_SEC", "1.2"))
        self._auto_barge_debounce_sec: float = float(
            os.getenv("AUTO_BARGE_DEBOUNCE_SEC", "0.5")
        )
        self._barge_start_guard_sec: float = float(
            os.getenv("BARGE_START_GUARD_SEC", "0.25")
        )
        self._auto_barge_confirm_window_sec: float = float(
            os.getenv("AUTO_BARGE_CONFIRM_WINDOW_SEC", "1.5")
        )
        self._last_auto_barge_at: float = 0.0
        self._pending_auto_barge_at: float | None = None
        self._tts_active: bool = False

        # Barge-in control:
        # _llm_lock serialises LLM calls so a new transcript from the STT task
        # never starts a second LLM response while the first is still dispatching.
        # _interrupted is set the instant speech is detected; _dispatch_llm_response
        # checks it before sending audio and before each stroke batch so the
        # remainder of Ada's current response is silently dropped.
        self._llm_lock = asyncio.Lock()
        self._interrupted: bool = False

        # Proactive board review:
        # _last_interaction_at tracks the last time the student (or session start)
        # produced a message, so we know when they've been drawing silently.
        # _last_analysis_at rate-limits how often Ada reviews the board unprompted.
        # _wait_for_student mirrors the LLM flag — proactive review only fires when
        # Ada explicitly asked the student to show their work on the board.
        self._last_interaction_at: float = time.time()
        self._last_analysis_at: float = 0.0
        self._wait_for_student: bool = False

        # STT utterance assembly:
        # Deepgram can emit multiple final chunks for one human sentence.
        # Buffer and merge adjacent chunks briefly so Ada responds to the
        # complete thought instead of cutting off mid-question.
        self._stt_merge_window_sec: float = float(os.getenv("STT_MERGE_WINDOW_SEC", "0.8"))
        self._stt_buffer: list[str] = []
        self._stt_flush_task: asyncio.Task | None = None

    def cleanup(self) -> None:
        """
        Cancel any background tasks when the client WebSocket closes.
        Called by main.py on WebSocketDisconnect so the STT task does not
        fire callbacks against a dead socket.
        """
        if self._stt_task and not self._stt_task.done():
            self._stt_task.cancel()
        if self._stt_flush_task and not self._stt_flush_task.done():
            self._stt_flush_task.cancel()
        # Drain the audio queue with a sentinel so _send_audio exits cleanly
        if self._audio_queue is not None:
            try:
                self._audio_queue.put_nowait(None)
            except asyncio.QueueFull:
                pass
            self._audio_queue = None

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
        elif msg_type == "barge_in":
            await self._on_speech_start(source="manual")
        else:
            await self.websocket.send_json(
                {"type": "error", "message": f"Unknown message type: {msg_type}"}
            )

    # ── Session / LLM ────────────────────────────────────────────────────────

    async def _handle_session_start(self, data: dict) -> None:
        self.session.current_subject = data.get("subject", "")
        self.session.is_active = True
        self.session.tutor_mode = "listening"
        self._last_interaction_at = time.time()

        subject_label = self.session.current_subject or "whatever I need"
        self.session.add_user_turn(
            f"Hey, let's work on {subject_label}.",
            time.time(),
        )

        async with self._llm_lock:
            self._interrupted = False  # clear any stale barge-in from a previous response

            tts_task: asyncio.Task | None = None
            tts_started = asyncio.Event()

            async def on_speech_ready(text: str) -> None:
                nonlocal tts_task
                self.session.add_assistant_turn(text, time.time())
                await self.websocket.send_json({"type": "speech_text", "text": text})
                tts_task = asyncio.create_task(self._stream_tts_chunks(text, tts_started))

            llm_response = await self.llm.get_response(
                self._messages_with_board_context(),
                on_speech_ready=on_speech_ready,
            )
            await self._dispatch_llm_response(llm_response, tts_task, tts_started)

    async def _handle_transcript(self, data: dict) -> None:
        text = data.get("text", "").strip()
        if not text:
            return

        # Add to history immediately (outside the lock) so the turn is in
        # context even if another handler acquires the lock first.
        self.session.add_user_turn(text, time.time())
        self._last_interaction_at = time.time()
        self._wait_for_student = False  # student spoke — stop watching the board

        latest_snapshot = (
            self.session.board_snapshots[-1].image_base64
            if self.session.board_snapshots
            else None
        )

        # Acquire the lock so only one LLM call runs at a time.
        # If a previous response is still dispatching (e.g. sending strokes),
        # we wait here — _interrupted causes it to exit early quickly.
        async with self._llm_lock:
            self._interrupted = False  # this turn owns the response now

            tts_task: asyncio.Task | None = None
            tts_started = asyncio.Event()

            async def on_speech_ready(text: str) -> None:
                nonlocal tts_task
                self.session.add_assistant_turn(text, time.time())
                await self.websocket.send_json({"type": "speech_text", "text": text})
                tts_task = asyncio.create_task(self._stream_tts_chunks(text, tts_started))

            llm_response = await self.llm.get_response(
                self._messages_with_board_context(),
                board_snapshot_b64=latest_snapshot,
                on_speech_ready=on_speech_ready,
            )
            await self._dispatch_llm_response(llm_response, tts_task, tts_started)

    async def _handle_board_snapshot(self, data: dict) -> None:
        image_b64 = data.get("image_base64", "")
        if not image_b64:
            return
        width = data.get("width")
        height = data.get("height")
        if isinstance(width, (int, float)) and width > 200:
            self.session.board_width = int(width)
        if isinstance(height, (int, float)) and height > 200:
            self.session.board_height = int(height)
        self.session.add_board_snapshot(image_b64, time.time())
        await self.websocket.send_json(
            {"type": "snapshot_received", "count": len(self.session.board_snapshots)}
        )

        # Proactive mistake detection: only triggers when Ada explicitly asked
        # the student to show their work (wait_for_student=True). This prevents
        # the analyzer from hijacking normal voice conversation turns.
        now = time.time()
        silent_for = now - self._last_interaction_at
        since_last_check = now - self._last_analysis_at

        if (
            self._wait_for_student       # Ada asked the student to work on the board
            and silent_for > 6.0         # student has been drawing, not just pausing to think
            and since_last_check > 15.0  # rate-limit: at most once per 15 s
            and not self._llm_lock.locked()  # Ada isn't already responding
        ):
            self._last_analysis_at = now  # claim the slot before task starts
            asyncio.create_task(
                self._proactive_board_analysis(image_b64, trigger_time=now)
            )

    async def _proactive_board_analysis(
        self, image_b64: str, trigger_time: float
    ) -> None:
        """
        Runs as a background task when the student has been drawing silently.
        Sends the board snapshot to the LLM with a focused check-for-mistakes
        prompt; Ada responds with corrections in red using the same handwriting
        strokes (color="#FF0000") or encouragement if everything is correct.

        A synthetic "[checking my work on the board]" user turn is added to the
        conversation history to keep the alternating-turn structure valid and
        give Ada natural context for future turns.  It is removed silently if
        the LLM finds nothing to say (empty board / only Ada's own notes).
        """
        async with self._llm_lock:
            # If the student spoke after this analysis was scheduled, skip it —
            # their new message will already prompt a fresh response from Ada.
            if self._last_interaction_at > trigger_time:
                return

            self._interrupted = False

            # Synthetic user turn — represents the student pausing to let Ada check.
            # Added inside the lock so it's never orphaned without an assistant reply.
            self.session.add_user_turn("[checking my work on the board]", time.time())

            tts_task: asyncio.Task | None = None
            tts_started = asyncio.Event()

            async def on_speech_ready(text: str) -> None:
                nonlocal tts_task
                if not text.strip():
                    return
                self.session.add_assistant_turn(text, time.time())
                await self.websocket.send_json({"type": "speech_text", "text": text})
                tts_task = asyncio.create_task(self._stream_tts_chunks(text, tts_started))

            # Use the latest snapshot in case new drawing happened while waiting
            current_image = (
                self.session.board_snapshots[-1].image_base64
                if self.session.board_snapshots
                else image_b64
            )

            llm_response = await self.llm.get_response(
                self._messages_with_board_context(),
                board_snapshot_b64=current_image,
                on_speech_ready=on_speech_ready,
            )

            speech = llm_response.get("speech", "").strip()
            board_actions = llm_response.get("board_actions", [])

            if not speech and not board_actions:
                # Nothing to say — remove the synthetic turn to keep history clean
                history = self.session.conversation_history
                if history and history[-1].content == "[checking my work on the board]":
                    history.pop()
                return

            await self._dispatch_llm_response(llm_response, tts_task, tts_started)

    # ── STT / Audio ──────────────────────────────────────────────────────────

    async def _handle_audio_start(self) -> None:
        """Open a Deepgram session as a background task."""
        if self._stt_task and not self._stt_task.done():
            self._stt_task.cancel()

        self._audio_queue = asyncio.Queue()
        self._stt_task = asyncio.create_task(self._run_stt_session())

    async def _run_stt_session(self) -> None:
        """
        Run Deepgram STT in a loop so it auto-reconnects if the connection drops
        (e.g. Deepgram closes despite KeepAlives, or a transient network error).
        Exits when audio_stop sets _audio_queue to None.
        """
        while self._audio_queue is not None:
            await self.stt.stream_session(
                self._audio_queue,
                self._on_stt_transcript,
                self._on_speech_start,
            )
            if self._audio_queue is not None:
                print("[STT] Session ended unexpectedly — reconnecting in 1 s…")
                # Drain stale chunks so reconnect starts with a clean slate
                q = self._audio_queue
                while not q.empty():
                    try:
                        q.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                await asyncio.sleep(1.0)

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
        # Flush any buffered final transcript when mic streaming stops.
        await self._flush_stt_buffer()

    async def _emit_barge_in(self) -> None:
        self._interrupted = True
        self._last_tts_sent_at = 0.0  # reset cooldown so barge-in transcript is processed
        await self.websocket.send_json({"type": "barge_in"})

    async def _on_speech_start(self, source: str = "stt") -> None:
        """
        Deepgram detected the start of speech (fires before the transcript is ready).
        Tell the frontend to cut Ada's audio and strokes immediately — barge-in.
        Set _interrupted so _dispatch_llm_response drops the rest of Ada's response.
        Also reset the echo cooldown so the upcoming transcript is not suppressed.
        """
        now = time.time()
        if source == "manual":
            self._pending_auto_barge_at = None
            await self._emit_barge_in()
            return

        if source == "stt":
            if not self._tts_active:
                return
            if now - self._last_auto_barge_at < self._auto_barge_debounce_sec:
                return
            if (
                self._last_tts_started_at > 0
                and now - self._last_tts_started_at < self._barge_start_guard_sec
            ):
                return
            # Do not cut Ada immediately on VAD alone — wait for a real transcript
            # to confirm the student actually spoke (avoids self-interruptions).
            self._pending_auto_barge_at = now

    async def _on_stt_transcript(self, text: str) -> None:
        """
        Called by STTClient when a final transcript arrives from Deepgram.
        Skips transcripts that arrive too soon after Ada's TTS (likely echo).

        Uses create_task rather than awaiting _handle_transcript directly so the
        STT recv loop is never blocked — Deepgram messages (including the next
        SpeechStarted for another barge-in) keep flowing immediately.
        The _llm_lock inside _handle_transcript serialises concurrent calls.
        """
        import time as _time
        now = _time.time()

        # Confirm pending auto-barge-in only when we got a real transcript.
        if self._pending_auto_barge_at is not None:
            pending_age = now - self._pending_auto_barge_at
            if self._tts_active and pending_age <= self._auto_barge_confirm_window_sec:
                self._last_auto_barge_at = now
                await self._emit_barge_in()
            self._pending_auto_barge_at = None

        elapsed = _time.time() - self._last_tts_sent_at
        if elapsed < self._echo_cooldown:
            print(f"STT echo suppressed ({elapsed:.2f}s after TTS): {text!r}")
            return

        # Merge adjacent final chunks into one utterance.
        self._stt_buffer.append(text.strip())
        if self._stt_flush_task and not self._stt_flush_task.done():
            self._stt_flush_task.cancel()
        self._stt_flush_task = asyncio.create_task(self._flush_stt_buffer_after_delay())

    async def _flush_stt_buffer_after_delay(self) -> None:
        try:
            await asyncio.sleep(self._stt_merge_window_sec)
            await self._flush_stt_buffer()
        except asyncio.CancelledError:
            return

    async def _flush_stt_buffer(self) -> None:
        parts = [p for p in self._stt_buffer if p]
        if not parts:
            return
        self._stt_buffer = []
        merged = " ".join(parts).strip()
        if not merged:
            return

        try:
            await self.websocket.send_json({"type": "transcript_interim", "text": merged})
            asyncio.create_task(self._handle_transcript({"text": merged}))
        except Exception:
            # WebSocket already closed — discard silently
            pass

    # ── Board state helpers ───────────────────────────────────────────────────

    def _messages_with_board_context(self) -> list[dict]:
        """
        Return the conversation history with a board-state note appended to the
        last user message, so the LLM knows where Ada has already written and
        where free space remains on the canvas.
        """
        messages = self.session.to_anthropic_messages()
        ctx = self.session.get_board_state_context()
        if not ctx or not messages:
            return messages

        # Find the last user message and append the note to its content.
        for i in reversed(range(len(messages))):
            if messages[i]["role"] == "user":
                messages = list(messages)  # shallow copy to avoid mutating session state
                messages[i] = dict(messages[i], content=messages[i]["content"] + f"\n{ctx}")
                break
        return messages

    def _normalize_board_actions(self, board_actions: list) -> list:
        """
        Normalize LLM board actions into drawable lines that fit the board width.
        Splits long write content into wrapped line actions to avoid right-edge
        clipping and accidental overlap from unhandled newlines.
        """
        if not board_actions:
            return []

        usable_width = max(360, self.session.board_width - 160)
        # Caveat handwriting averages roughly 12-14 px per character.
        chars_per_line = max(18, min(80, int(usable_width / 13)))
        line_step = 52

        normalized: list = []
        for action in board_actions:
            if action.get("type") != "write":
                normalized.append(action)
                continue

            raw_content = action.get("content", "")
            content = raw_content if isinstance(raw_content, str) else str(raw_content)
            if not content.strip():
                continue

            pos = action.get("position")
            if isinstance(pos, dict):
                base_x = float(pos.get("x", 80))
                base_y = float(pos.get("y", 140))
            else:
                base_x, base_y = 80.0, 140.0

            # Keep x within visible board bounds.
            max_x = max(80.0, float(self.session.board_width - 220))
            base_x = min(max(20.0, base_x), max_x)

            logical_lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
            if not logical_lines:
                logical_lines = [content.strip()]

            rendered_lines: list[str] = []
            for line in logical_lines:
                wrapped = textwrap.wrap(
                    line,
                    width=chars_per_line,
                    break_long_words=False,
                    break_on_hyphens=False,
                )
                rendered_lines.extend(wrapped or [line])

            color = action.get("color", "#000000")
            fmt = action.get("format", "text")
            for idx, line in enumerate(rendered_lines):
                normalized.append(
                    {
                        "type": "write",
                        "content": line,
                        "format": fmt,
                        "position": {"x": base_x, "y": base_y + idx * line_step},
                        "color": color,
                    }
                )

        return normalized

    def _rebase_board_actions(self, board_actions: list) -> list:
        """
        Shift write-action y-coordinates so new content starts below Ada's
        existing writing, regardless of what y-coords the LLM picked.
        Prepends a 'clear' action when the remaining canvas space is too small.
        """
        write_actions = [a for a in board_actions if a.get("type") == "write"]
        if not write_actions or self.session.board_next_y == 0:
            return board_actions

        ys = [
            a["position"]["y"]
            for a in write_actions
            if isinstance(a.get("position"), dict)
            and isinstance(a["position"].get("y"), (int, float))
        ]
        if not ys:
            return board_actions

        min_y = min(ys)
        target_y = self.session.board_next_y + 20  # 20px gap after existing content

        # LLM already placed content below the cursor — no rebasing needed
        if min_y >= target_y:
            return board_actions

        content_height = max(ys) - min_y

        # Canvas can't fit the new block — auto-clear and start fresh
        board_limit_y = max(280, self.session.board_height - 20)
        if target_y + content_height > board_limit_y:
            self.session.board_next_y = 0
            self.session.board_next_x = 80
            return [{"type": "clear"}, *board_actions]

        # Shift all write-action y-coordinates down by the required offset
        offset = int(target_y - min_y)
        result = []
        for action in board_actions:
            if action.get("type") == "write" and isinstance(action.get("position"), dict):
                action = dict(action, position={
                    "x": action["position"].get("x", 80),
                    "y": action["position"]["y"] + offset,
                })
            result.append(action)
        return result

    def _update_board_cursor(self, board_actions: list) -> None:
        """
        After Ada writes, record the lowest y-coordinate used so the orchestrator
        knows where free space starts for the next response.
        Handles 'clear' inline (resets the cursor, then continues scanning writes).
        """
        max_y = self.session.board_next_y
        for action in board_actions:
            if action.get("type") == "clear":
                max_y = 0
                self.session.board_next_x = 80
            elif action.get("type") == "write":
                pos = action.get("position", {})
                if isinstance(pos, dict):
                    y = pos.get("y", 0)
                    if isinstance(y, (int, float)):
                        # 50px accounts for ~26px cap height + line spacing
                        max_y = max(max_y, int(y) + 50)
        self.session.board_next_y = max_y

    # ── LLM response dispatch ────────────────────────────────────────────────

    async def _stream_tts_chunks(self, text: str, started: asyncio.Event) -> None:
        """
        Stream TTS bytes to the client as they arrive so playback can begin
        before full synthesis completes.
        """
        first_chunk_sent = False
        try:
            async for chunk in self.tts.stream(text):
                if self._interrupted:
                    break
                if not chunk:
                    continue
                audio_b64 = base64.b64encode(chunk).decode("utf-8")
                await self.websocket.send_json({"type": "audio_chunk", "data": audio_b64})
                if not first_chunk_sent:
                    self._last_tts_started_at = time.time()
                    self._tts_active = True
                self._last_tts_sent_at = time.time()
                if not first_chunk_sent:
                    first_chunk_sent = True
                    started.set()
        except Exception as exc:
            print(f"[TTS] stream failed: {exc}")
        finally:
            self._tts_active = False
            self._pending_auto_barge_at = None
            started.set()

    async def _dispatch_llm_response(
        self,
        llm_response: dict,
        tts_task: asyncio.Task | None = None,
        tts_started: asyncio.Event | None = None,
    ) -> None:
        """
        Natural professor sync: audio plays first, writing animates concurrently.

        Flow:
          1. Synthesize all handwriting strokes (TTS is running in background).
          2. Calibrate each stroke's animation_speed so all writing finishes in
             roughly the same time as Ada's speech.
          3. Await TTS → send audio so speaking starts immediately.
          4. Send strokes right after → animation begins while Ada is talking.

        This matches how a real professor works: they start speaking, then begin
        writing while they talk, finishing both at about the same time.
        """
        speech = llm_response.get("speech", "")
        raw_actions = llm_response.get("board_actions", [])
        board_actions = self._rebase_board_actions(self._normalize_board_actions(raw_actions))
        tutor_state = llm_response.get("tutor_state", "listening")

        self.session.tutor_mode = tutor_state

        # Fallback: start TTS if on_speech_ready didn't fire (e.g. empty speech).
        if speech and tts_task is None:
            self.session.add_assistant_turn(speech, time.time())
            await self.websocket.send_json({"type": "speech_text", "text": speech})
            tts_started = asyncio.Event()
            tts_task = asyncio.create_task(self._stream_tts_chunks(speech, tts_started))

        # ── Step 1: Synthesize all strokes, collect without sending yet ──────
        print(f"[Orchestrator] Processing {len(board_actions)} board_action(s)")
        pending: list[tuple[str, dict]] = []  # (msg_type, payload)

        for action in board_actions:
            if action.get("type") == "write":
                raw_content = action.get("content", "")
                text_content = raw_content if isinstance(raw_content, str) else str(raw_content)
                content_format = action.get("format", "text")

                raw_pos = action.get("position", {})
                if isinstance(raw_pos, dict):
                    position = {
                        "x": float(raw_pos.get("x", 100)),
                        "y": float(raw_pos.get("y", 100)),
                    }
                else:
                    position = {"x": 100, "y": 100}

                if content_format == "latex":
                    max_width = max(240.0, float(self.session.board_width - 180))
                    stroke_data = await self.latex.convert(
                        latex=text_content,
                        color=action.get("color", "#000000"),
                        position=position,
                        max_width_px=max_width,
                    )
                else:
                    stroke_data = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda t=text_content, c=action.get("color", "#000000"), p=position: (
                            self.handwriting.synthesize(text=t, color=c, position=p)
                        ),
                    )
                pending.append(("strokes", stroke_data.to_dict()))
            else:
                pending.append(("board_action", action))

        # ── Step 2: Calibrate animation speed to match speech duration ────────
        # Estimate how long Ada will speak (~2.4 words/second, min 1.5 s).
        # Spread that time evenly across all write actions so writing finishes
        # at roughly the same moment as speaking.
        write_payloads = [p for typ, p in pending if typ == "strokes"]
        if write_payloads and speech:
            speech_words = len(speech.split())
            speech_duration = max(1.5, speech_words / 2.4)
            target_per_action = speech_duration / len(write_payloads)

            for payload in write_payloads:
                total_pts = sum(len(s["points"]) for s in payload["strokes"])
                if total_pts > 0:
                    # animation_speed = points drawn per frame pair at 60 fps
                    payload["animation_speed"] = max(
                        1.0, round(total_pts / (target_per_action * 60 * 2), 2)
                    )

        # ── Step 3: Prefer audio-first, but don't stall writing indefinitely ──
        if tts_started is not None:
            try:
                await asyncio.wait_for(tts_started.wait(), timeout=0.8)
            except asyncio.TimeoutError:
                pass

        # ── Step 4: Send strokes right after → writing begins while Ada talks ─
        # Stop early if the user barged in; track only the actions actually sent
        # so the board cursor reflects what was genuinely drawn.
        sent_actions: list = []
        for (msg_type, payload), action in zip(pending, board_actions):
            if self._interrupted:
                break  # student is speaking — drop remaining strokes
            if msg_type == "strokes":
                await self.websocket.send_json({"type": "strokes", "strokes": payload})
            else:
                await self.websocket.send_json({"type": "board_action", "action": payload})
            sent_actions.append(action)

        # Update board cursor only for actions that were actually drawn.
        self._update_board_cursor(sent_actions)

        # Notify the frontend of the final tutor state and whether to wait for
        # the student (so the UI can show a "your turn" cue).
        wait_for_student = llm_response.get("wait_for_student", False)
        self._wait_for_student = bool(wait_for_student)
        await self.websocket.send_json({
            "type": "state_update",
            "tutor_state": tutor_state,
            "wait_for_student": wait_for_student,
        })

        # Ensure background TTS task errors are surfaced in this handler.
        if tts_task is not None:
            await tts_task
