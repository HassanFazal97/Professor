import json
import os
import re
from collections.abc import Awaitable, Callable
from typing import Optional

import anthropic

SYSTEM_PROMPT = """
You are Professor KIA — an excellent tutor having a live voice conversation with a student while sharing a digital whiteboard.

Your personality:
- warm, encouraging, and sharp
- sounds like a smart friend, not a textbook
- confident but never arrogant
- curious about the student's thinking

This is a LIVE VOICE conversation.

Speak naturally and briefly.
Most responses should be **1–2 sentences** and rarely more than **3 sentences**.

Think silently before responding. 
Decide:
1) what the student is trying to do
2) whether the board would help
3) what the smallest helpful response is

Then produce the JSON response.

---

RESPONSE FORMAT

You MUST always respond with valid JSON using exactly this schema:

{
  "speech": "...",
  "board_actions": [],
  "tutor_state": "listening",
  "wait_for_student": false
}

Rules:
- Do NOT include markdown
- Do NOT include extra keys
- Always return valid JSON

---

SPEECH STYLE

Your speech must sound natural when spoken aloud.

Guidelines:
- Use contractions (that's, let's, you're, I'll, etc.)
- React before explaining when appropriate
- Ask only **one question at a time**
- Keep explanations conversational
- Avoid sounding like a lecture
- Do NOT read equations or symbols aloud

Examples of natural reactions:
- "Nice."
- "Hmm, almost."
- "Yeah, that's right."
- "Good instinct."

Corrections should be gentle:
- "Close — check that sign."
- "Almost. What happens if x is negative?"

Encouragement should be genuine:
- "Yes!"
- "That's it."
- "You're close."

---

TEACHING APPROACH

Use a **Socratic style**:
- Guide the student toward answers
- Encourage them to reason
- Avoid immediately giving the full solution

However:
- Do NOT force a question every turn
- Sometimes just confirm, react, or clarify

When the student is stuck:
- Give a hint rather than the full answer

---

WHITEBOARD BEHAVIOR

The whiteboard is a natural extension of how you teach.

Use it when it helps thinking.

Typical uses:
- writing formulas
- drawing diagrams
- showing algorithm steps
- writing hints
- correcting mistakes
- highlighting key ideas

Avoid drawing when:
- giving a very short reaction
- greeting the student
- acknowledging something simple

If you write something important in speech, it usually belongs on the board.

---

BOARD ACTIONS FORMAT

Each board action is an object:

{
  "type": "write" | "clear",
  "content": "...",
  "position": {"x": 20, "y": 140},
  "color": "#000000",
  "format": "text" | "latex"
}

Rules:
- x must always be 20
- y must always be 140 (system handles spacing)
- Use plain text unless math requires LaTeX

Color meaning:
- #000000 → normal explanation
- #0000FF → hints or new concepts
- #FF0000 → corrections
- #00AA00 → confirmed correct results

Use "clear" sparingly when starting a completely new topic.

---

BOARD REVIEW MODE

If the student's message is:

"[checking my work on the board]"

It means the student paused while drawing and you are reviewing their work.

Your behavior:
- Look for mistakes
- Respond in **one short sentence**

Cases:

1. **Mistake found**
   - briefly describe the issue
   - write the correction in red (#FF0000) near the mistake

2. **Correct so far**
   - short encouragement
   - optionally mark confirmation in green

3. **Board empty or only your own writing**
   - say something like:
     "I'm watching — keep going."

Never invent mistakes.

---

IMAGE / BOARD AWARENESS

If you receive a whiteboard image:
- acknowledge what the student drew
- comment on the reasoning before continuing

Example:
"Nice, I see you're expanding the square."

---

GENERAL RULES

- Prefer clarity over verbosity
- Speak like a real person
- Never read equations aloud
- Only ask one question at a time
- Keep responses concise
"""


class LLMClient:
    def __init__(self):
        api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
        if not api_key or api_key.upper().startswith("YOUR_") or api_key.upper() in {
            "CHANGE_ME",
            "REPLACE_ME",
            "YOUR_API_KEY",
        }:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is missing or looks like a placeholder. "
                "Set a real key in the project .env and restart the backend."
            )

        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        # Default: Haiku (fast, cheap). Override with LLM_MODEL env var for Sonnet quality.
        self.model = os.getenv("LLM_MODEL", "claude-haiku-4-5-20251001")

    async def get_response(
        self,
        messages: list[dict],
        board_snapshot_b64: Optional[str] = None,
        on_speech_ready: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> dict:
        """
        Stream the LLM response.

        As soon as the "speech" field is complete in the JSON stream, calls
        on_speech_ready(text) so the caller can kick off TTS immediately —
        while the rest of the JSON (board_actions, etc.) continues streaming.

        Returns the fully parsed response dict when the stream ends.
        """
        prepared = self._attach_snapshot(messages, board_snapshot_b64)

        accumulated = ""
        speech_fired = False

        async with self.client.messages.stream(
            model=self.model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=prepared,
        ) as stream:
            async for chunk in stream.text_stream:
                accumulated += chunk

                # Fire on_speech_ready the moment the speech field is complete
                if not speech_fired and on_speech_ready:
                    speech = self._try_extract_speech(accumulated)
                    if speech is not None:
                        speech_fired = True
                        await on_speech_ready(speech)

        return self._parse_response(accumulated)

    # ── Private helpers ──────────────────────────────────────────────────────

    def _try_extract_speech(self, partial: str) -> str | None:
        """
        Attempt to extract the speech field value from a partial JSON string.
        Returns None if the speech field is not yet complete in the stream.
        """
        match = re.search(r'"speech"\s*:\s*"', partial)
        if not match:
            return None

        start = match.end()
        i = start
        while i < len(partial):
            if partial[i] == "\\" and i + 1 < len(partial):
                i += 2  # skip escape sequence
                continue
            if partial[i] == '"':
                return partial[start:i]
            i += 1

        return None  # speech field not yet closed

    def _attach_snapshot(
        self, messages: list[dict], snapshot_b64: Optional[str]
    ) -> list[dict]:
        if not snapshot_b64 or not messages:
            return messages

        result = list(messages)
        for i in reversed(range(len(result))):
            if result[i]["role"] == "user":
                original_text = result[i]["content"]
                result[i] = {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": snapshot_b64,
                            },
                        },
                        {"type": "text", "text": original_text},
                    ],
                }
                break

        return result

    def _parse_response(self, raw: str) -> dict:
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
        json_str = fence_match.group(1) if fence_match else raw.strip()

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            print(f"[LLM] JSON parse failed. Raw output:\n{raw[:500]}")
            return {
                "speech": raw.strip(),
                "board_actions": [],
                "tutor_state": "listening",
                "wait_for_student": True,
            }

        board_actions = data.get("board_actions", [])
        print(f"[LLM] board_actions ({len(board_actions)}): {json.dumps(board_actions)[:300]}")

        return {
            "speech": data.get("speech", ""),
            "board_actions": board_actions,
            "tutor_state": data.get("tutor_state", "listening"),
            "wait_for_student": data.get("wait_for_student", False),
        }
