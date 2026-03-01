import asyncio
import json
import os
import ssl
from collections.abc import Callable, Coroutine
from typing import Any

import aiohttp
import certifi

_SSL_CTX = ssl.create_default_context(cafile=certifi.where())

DEEPGRAM_WS_URL = "wss://api.deepgram.com/v1/listen"

# Minimum confidence for a transcript to be processed.
# Genuine speech from Nova-2 is usually > 0.8; background noise is much lower.
MIN_CONFIDENCE = float(os.getenv("STT_MIN_CONFIDENCE", "0.50"))

# Minimum number of words.
# Keep this at 1 so natural interjections ("yes", "wait", "no") are not dropped.
MIN_WORDS = int(os.getenv("STT_MIN_WORDS", "1"))

# For single-word transcripts, require higher confidence to reduce false
# barge-ins from background noise and speaker bleed.
MIN_SINGLE_WORD_CONFIDENCE = float(os.getenv("STT_SINGLE_WORD_MIN_CONFIDENCE", "0.70"))
FINAL_AFTER_CLOSE_WAIT_SEC = float(os.getenv("STT_FINAL_AFTER_CLOSE_WAIT_SEC", "2.5"))


class STTClient:
    """
    Deepgram Nova-2 streaming STT proxy with barge-in support.

    Callers provide two callbacks:
      on_final_transcript(text)  — called when user finishes a full utterance
      on_speech_start()          — called the instant Deepgram detects voice
                                   (use this for barge-in: stop Ada immediately)
    """

    def __init__(self):
        self.api_key = os.getenv("DEEPGRAM_API_KEY", "").strip()
        self.enabled = bool(self.api_key)
        self.model = os.getenv("DEEPGRAM_MODEL", "nova-2").strip() or "nova-2"
        self.endpointing_ms = int(os.getenv("DEEPGRAM_ENDPOINTING_MS", "300"))

    def build_url(self) -> str:
        return (
            f"{DEEPGRAM_WS_URL}"
            f"?model={self.model}"
            "&language=en-US"
            "&punctuate=true"
            "&smart_format=true"
            # VAD events — fires SpeechStarted the instant voice is detected,
            # before the transcript is ready. Used for barge-in.
            "&vad_events=true"
            # Lower endpointing improves responsiveness in push-to-talk mode.
            f"&endpointing={self.endpointing_ms}"
            # Keep interim results so SpeechStarted events arrive in time.
            "&interim_results=true"
            "&encoding=opus"
            "&container=webm"
        )

    async def stream_session(
        self,
        audio_queue: asyncio.Queue,
        on_final_transcript: Callable[[str], Coroutine[Any, Any, None]],
        on_speech_start: Callable[[], Coroutine[Any, Any, None]] | None = None,
    ) -> None:
        """
        Open a Deepgram WebSocket, forward audio from audio_queue, and fire
        callbacks for voice-start and final transcripts.

        Exits cleanly when None is placed in the audio_queue.
        """
        if not self.enabled:
            return

        headers = {"Authorization": f"Token {self.api_key}"}

        try:
            connector = aiohttp.TCPConnector(ssl=_SSL_CTX)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.ws_connect(self.build_url(), headers=headers) as dg_ws:
                    send_task = asyncio.create_task(self._send_audio(dg_ws, audio_queue))
                    recv_task = asyncio.create_task(
                        self._recv_messages(dg_ws, on_final_transcript, on_speech_start)
                    )
                    # Wait until either side finishes.
                    done, pending = await asyncio.wait(
                        [send_task, recv_task],
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                    # If send finished first because we sent CloseStream (PTT release),
                    # keep recv alive briefly so Deepgram can deliver final Results.
                    send_finished = send_task in done and not send_task.cancelled()
                    send_exc = send_task.exception() if send_finished else None
                    if send_finished and send_exc is None and recv_task in pending:
                        try:
                            await asyncio.wait_for(recv_task, timeout=FINAL_AFTER_CLOSE_WAIT_SEC)
                        except asyncio.TimeoutError:
                            recv_task.cancel()
                            try:
                                await recv_task
                            except (asyncio.CancelledError, Exception):
                                pass
                        except (asyncio.CancelledError, Exception):
                            pass
                    else:
                        for task in pending:
                            task.cancel()
                            try:
                                await task
                            except (asyncio.CancelledError, Exception):
                                pass

                    # Surface any real exception from the finished tasks
                    for task in done:
                        if not task.cancelled():
                            exc = task.exception()
                            if exc is not None:
                                raise exc
        except Exception as e:
            import traceback
            print(f"STT stream error: {e}")
            traceback.print_exc()

    async def _send_audio(
        self, dg_ws: aiohttp.ClientWebSocketResponse, audio_queue: asyncio.Queue
    ) -> None:
        # Deepgram closes streaming connections after ~10 s of silence.
        # We send a KeepAlive JSON message every 8 s when no audio arrives so
        # the connection stays open while Ada is speaking (audio is gated
        # client-side during that window to prevent echo).
        _KEEPALIVE_INTERVAL = 8.0

        while True:
            try:
                chunk = await asyncio.wait_for(
                    audio_queue.get(), timeout=_KEEPALIVE_INTERVAL
                )
            except asyncio.TimeoutError:
                # No audio chunk arrived — ping Deepgram to prevent idle timeout
                try:
                    await dg_ws.send_str(json.dumps({"type": "KeepAlive"}))
                except Exception:
                    break  # Deepgram WS already closed; exit cleanly
                continue

            if chunk is None:
                await dg_ws.send_str(json.dumps({"type": "CloseStream"}))
                break
            await dg_ws.send_bytes(chunk)

    async def _recv_messages(
        self,
        dg_ws: aiohttp.ClientWebSocketResponse,
        on_final_transcript: Callable[[str], Coroutine[Any, Any, None]],
        on_speech_start: Callable[[], Coroutine[Any, Any, None]] | None,
    ) -> None:
        async for msg in dg_ws:
            # Exit cleanly on WebSocket close or error frames
            if msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR):
                break
            if msg.type != aiohttp.WSMsgType.TEXT:
                continue

            try:
                data = json.loads(msg.data)
            except (json.JSONDecodeError, TypeError):
                continue

            # Guard: Deepgram always sends dicts, but be defensive
            if not isinstance(data, dict):
                continue

            msg_type = data.get("type")

            # ── Barge-in: voice detected before transcript is ready ───────────
            if msg_type == "SpeechStarted" and on_speech_start:
                await on_speech_start()
                continue

            if msg_type != "Results":
                continue

            # ── Final transcript ──────────────────────────────────────────────
            alternatives = data.get("channel", {}).get("alternatives", [])
            if not alternatives:
                continue

            transcript = alternatives[0].get("transcript", "").strip()
            confidence = alternatives[0].get("confidence", 0.0)
            is_final = data.get("is_final", False)

            if not (transcript and is_final):
                continue

            # Filter noise: too low confidence or too few words
            word_count = len(transcript.split())
            if confidence < MIN_CONFIDENCE or word_count < MIN_WORDS:
                print(
                    f"STT filtered: {transcript!r} "
                    f"(confidence={confidence:.2f}, words={word_count})"
                )
                continue

            if word_count == 1 and confidence < MIN_SINGLE_WORD_CONFIDENCE:
                print(
                    f"STT filtered: {transcript!r} "
                    f"(confidence={confidence:.2f}, words={word_count})"
                )
                continue

            await on_final_transcript(transcript)
