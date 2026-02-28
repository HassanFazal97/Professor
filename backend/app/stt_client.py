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
MIN_CONFIDENCE = 0.60

# Minimum number of words — filters out single-word ghost transcripts from noise.
MIN_WORDS = 3


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

    def build_url(self) -> str:
        return (
            f"{DEEPGRAM_WS_URL}"
            "?model=nova-2"
            "&language=en-US"
            "&punctuate=true"
            "&smart_format=true"
            # VAD events — fires SpeechStarted the instant voice is detected,
            # before the transcript is ready. Used for barge-in.
            "&vad_events=true"
            # Longer endpointing reduces false triggers from brief noises.
            "&endpointing=500"
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
                    await asyncio.gather(
                        self._send_audio(dg_ws, audio_queue),
                        self._recv_messages(dg_ws, on_final_transcript, on_speech_start),
                    )
        except Exception as e:
            import traceback
            print(f"STT stream error: {e}")
            traceback.print_exc()

    async def _send_audio(
        self, dg_ws: aiohttp.ClientWebSocketResponse, audio_queue: asyncio.Queue
    ) -> None:
        while True:
            chunk = await audio_queue.get()
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

            await on_final_transcript(transcript)
