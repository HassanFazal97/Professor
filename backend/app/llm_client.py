import os
from typing import Optional

import anthropic

SYSTEM_PROMPT = """You are Professor Ada — a warm, Socratic AI tutor. You help students learn by asking guiding questions before giving answers.

Your responses MUST be valid JSON in this exact format:
{
  "speech": "What you say out loud to the student",
  "board_actions": [
    {
      "type": "write",
      "content": "text or LaTeX to write",
      "format": "text|latex",
      "position": {"x": 0, "y": 0},
      "color": "#000000"
    }
  ],
  "tutor_state": "listening|guiding|demonstrating|evaluating",
  "wait_for_student": false
}

Color conventions:
- Red (#FF0000): corrections
- Blue (#0000FF): hints
- Green (#00AA00): correct work
- Black (#000000): new content

Always narrate whiteboard actions out loud as they happen. Be encouraging."""


class LLMClient:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.model = "claude-sonnet-4-5"

    async def get_response(
        self,
        messages: list[dict],
        board_snapshot_b64: Optional[str] = None,
    ) -> dict:
        """
        Send conversation + optional board snapshot to Claude and return parsed JSON response.

        Args:
            messages: Anthropic-format message list from session.to_anthropic_messages()
            board_snapshot_b64: Base64-encoded PNG of the current whiteboard state

        Returns:
            Parsed LLM response dict with speech, board_actions, tutor_state, wait_for_student
        """
        # TODO: implement full vision call with board snapshot
        # If board_snapshot_b64 is provided, attach it as an image content block
        # to the last user message.

        # Stub — return a placeholder response
        return {
            "speech": "Let me think about that...",
            "board_actions": [],
            "tutor_state": "listening",
            "wait_for_student": True,
        }

    def _build_vision_message(self, text: str, image_b64: str) -> dict:
        """Construct an Anthropic message with both text and image content."""
        return {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": image_b64,
                    },
                },
                {"type": "text", "text": text},
            ],
        }
