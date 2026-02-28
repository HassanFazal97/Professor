import os
import ssl

import aiohttp
import certifi

_SSL_CTX = ssl.create_default_context(cafile=certifi.where())

ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1/text-to-speech"


class TTSClient:
    def __init__(self):
        self.api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
        self.voice_id = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # Rachel
        self.enabled = bool(self.api_key)

    async def synthesize(self, text: str) -> bytes:
        """
        Convert text to speech via ElevenLabs and return complete mp3 bytes.

        Returns empty bytes if no API key is configured, so the rest of the
        session continues normally without audio.
        """
        if not self.enabled or not text.strip():
            return b""

        try:
            chunks: list[bytes] = []
            async for chunk in self._stream(text):
                chunks.append(chunk)
            return b"".join(chunks)
        except Exception as e:
            print(f"TTS error: {e}")
            return b""

    async def _stream(self, text: str):
        """POST to ElevenLabs streaming endpoint and yield raw mp3 chunks."""
        url = f"{ELEVENLABS_API_URL}/{self.voice_id}/stream"
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": text,
            "model_id": "eleven_flash_v2_5",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "use_speaker_boost": True,
            },
        }
        connector = aiohttp.TCPConnector(ssl=_SSL_CTX)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                resp.raise_for_status()
                async for chunk in resp.content.iter_chunked(4096):
                    yield chunk
