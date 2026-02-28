import os

import aiohttp

DEEPGRAM_WS_URL = "wss://api.deepgram.com/v1/listen"


class STTClient:
    """
    Deepgram Nova-2 streaming STT proxy.

    The frontend connects to our backend WebSocket which proxies audio frames
    to Deepgram and forwards transcripts back to the frontend.
    """

    def __init__(self):
        self.api_key = os.getenv("DEEPGRAM_API_KEY", "")

    def build_deepgram_url(self) -> str:
        """Build the Deepgram WebSocket URL with query params."""
        params = (
            "model=nova-2"
            "&language=en-US"
            "&punctuate=true"
            "&interim_results=true"
            "&endpointing=300"
        )
        return f"{DEEPGRAM_WS_URL}?{params}"

    def get_auth_headers(self) -> dict:
        return {"Authorization": f"Token {self.api_key}"}

    # TODO: implement proxy logic
    # The orchestrator will:
    # 1. Open a Deepgram WebSocket using build_deepgram_url() + get_auth_headers()
    # 2. Forward raw audio bytes from the frontend WebSocket to Deepgram
    # 3. Parse Deepgram transcript responses and emit { type: "transcript", text } to the frontend
