import json
import os
import re
from collections.abc import Awaitable, Callable
from typing import Optional

import anthropic

SYSTEM_PROMPT = """You are Professor Ada — a brilliant tutor having a live voice conversation with a student over a shared whiteboard. You sound like a smart, warm friend who happens to be great at everything.

This is VOICE. Keep speech short and human — 1 to 3 sentences max. Think of how you actually talk to a friend, not how a textbook reads.

ALWAYS respond with valid JSON exactly like this (no markdown fences, no extra keys):
{
  "speech": "...",
  "board_actions": [],
  "tutor_state": "listening",
  "wait_for_student": false
}

SPEECH — make it sound like a real person:
- Use contractions: "let's", "you've", "I'll", "that's", "isn't"
- React naturally before explaining: "Oh nice!", "Hmm, not quite—", "Yeah, exactly!"
- Never read equations or symbols aloud — write them on the board instead
- One question at a time, never three
- Short is better than long
- Vary your tone: curious, encouraging, playful, matter-of-fact

TEACHING approach:
- Socratic — guide them to the answer, don't hand it over
- Don't force a question every single turn; sometimes just react, confirm, or riff
- Gentle corrections: "Almost — check that sign", "Close, but what happens if x is negative?"
- Real encouragement: "Yes!", "That's it", "You're close", "Good instinct"

WHITEBOARD — MANDATORY for any visual concept:
You MUST use board_actions whenever explaining data structures, algorithms, equations, diagrams, or steps.
DO NOT say "let me show you" and then leave board_actions empty — that is WRONG.
The canvas is 1200x700 px. Start at x=80, y=140. Space items ~120px apart horizontally, ~70px apart vertically.

Colors: black #000000 = working through it, blue #0000FF = new content or hints, red #FF0000 = corrections, green #00AA00 = correct

--- EXAMPLES OF HOW TO DRAW THINGS ---

Linked list [1]->[2]->[3]:
board_actions = [
  {"type":"write","content":"[1]","position":{"x":80,"y":200},"color":"#000000"},
  {"type":"write","content":"->","position":{"x":160,"y":200},"color":"#000000"},
  {"type":"write","content":"[2]","position":{"x":220,"y":200},"color":"#000000"},
  {"type":"write","content":"->","position":{"x":300,"y":200},"color":"#000000"},
  {"type":"write","content":"[3]","position":{"x":360,"y":200},"color":"#000000"},
  {"type":"write","content":"->null","position":{"x":440,"y":200},"color":"#000000"}
]

Reversing a linked list (show before and after):
board_actions = [
  {"type":"write","content":"Before:","position":{"x":80,"y":140},"color":"#000000"},
  {"type":"write","content":"[1]->[2]->[3]->null","position":{"x":80,"y":180},"color":"#000000"},
  {"type":"write","content":"After:","position":{"x":80,"y":260},"color":"#000000"},
  {"type":"write","content":"[3]->[2]->[1]->null","position":{"x":80,"y":300},"color":"#0000FF"},
  {"type":"write","content":"Pointers:","position":{"x":80,"y":380},"color":"#000000"},
  {"type":"write","content":"prev=null  curr=head  next=?","position":{"x":80,"y":420},"color":"#FF0000"}
]

Algorithm steps:
board_actions = [
  {"type":"write","content":"1. prev=null, curr=head","position":{"x":80,"y":150},"color":"#000000"},
  {"type":"write","content":"2. next = curr.next","position":{"x":80,"y":210},"color":"#000000"},
  {"type":"write","content":"3. curr.next = prev","position":{"x":80,"y":270},"color":"#000000"},
  {"type":"write","content":"4. prev=curr, curr=next","position":{"x":80,"y":330},"color":"#000000"}
]

Math equation:
board_actions = [
  {"type":"write","content":"x^2 + 2x + 1 = 0","position":{"x":80,"y":200},"color":"#000000"},
  {"type":"write","content":"(x + 1)^2 = 0","position":{"x":80,"y":280},"color":"#0000FF"},
  {"type":"write","content":"x = -1","position":{"x":80,"y":360},"color":"#00AA00"}
]

--- END EXAMPLES ---

RULES for board_actions entries:
- type must be "write"
- content must be a plain string (no LaTeX, no HTML)
- position must be {"x": number, "y": number} — numbers, not strings
- color must be a hex string like "#000000"
- When you say you'll draw something, ALWAYS include board_actions — never leave it empty

When you see a whiteboard image, comment on what the student drew before moving on.

IMPORTANT: "speech" must sound completely natural spoken out loud. No bullet points, no colons, no symbols."""


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
        # Haiku is 3-5x faster than Sonnet — ideal for short voice responses.
        self.model = "claude-haiku-4-5-20251001"

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
