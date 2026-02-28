import os
from typing import AsyncIterator

import aiohttp

ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1/text-to-speech"


class TTSClient:
    def __init__(self):
        self.api_key = os.getenv("ELEVENLABS_API_KEY", "")
        self.voice_id = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # Rachel default

    async def stream_audio(self, text: str) -> AsyncIterator[bytes]:
        """
        Stream TTS audio from ElevenLabs for the given text.

        Yields raw audio bytes (mp3) in chunks suitable for streaming to the frontend.
        """
        # TODO: implement actual ElevenLabs streaming
        # Endpoint: POST /v1/text-to-speech/{voice_id}/stream
        # Headers: xi-api-key, Content-Type: application/json
        # Body: { "text": text, "model_id": "eleven_turbo_v2", "voice_settings": {...} }
        # Stream the response body and yield chunks

        # Stub — yield nothing
        return
        yield  # make this an async generator

    async def _post_stream(self, text: str) -> AsyncIterator[bytes]:
        """Internal: POST to ElevenLabs and stream response chunks."""
        url = f"{ELEVENLABS_API_URL}/{self.voice_id}/stream"
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": text,
            "model_id": "eleven_turbo_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                resp.raise_for_status()
                async for chunk in resp.content.iter_chunked(4096):
                    yield chunk
