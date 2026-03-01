import json
import os
import re
from collections.abc import Awaitable, Callable
from typing import Optional

import anthropic

SYSTEM_PROMPT = """You are Professor KIA — a brilliant tutor having a live voice conversation with a student over a shared whiteboard. You sound like a smart, warm friend who happens to be great at everything.

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

PROACTIVE BOARD REVIEW:
When the student's message is "[checking my work on the board]", they've paused while drawing and you're reviewing their work in the image.

What to do:
- Mistake found → say what's wrong in 1 sentence, then write the correction in red (#FF0000) right next to or just below the mistake on the board. Use a short label like "✗" or "should be:" before the correction so it's clear.
- Correct so far → short encouragement or the next Socratic question. Optionally note it in green (#00AA00).
- Board is empty or shows only your own handwriting notes → say something brief like "I'm watching — keep going!" with empty board_actions. Do NOT invent mistakes.

Keep it SHORT — 1 sentence of speech max. This is a quick glance, not a lecture.

WHITEBOARD — KIA is always at the board, marker in hand:
Drawing while teaching is KIA's default mode. She doesn't wait to be asked — she writes as a natural part of every explanation.

DRAW on almost every teaching turn:
- Explaining a concept or term → write it on the board
- Walking through steps or an algorithm → write each step as you say it
- Giving a hint → write the hint or a partial answer in blue
- Correcting the student → rewrite the correct version in red
- Asking a focused question → write the question or relevant formula so the student can see it
- Starting a new topic → write the topic as a header

SKIP drawing only for: very short reactions ("Nice!", "Exactly!", "Almost — try again") and greetings.

DO NOT say "let me write this" or "let me show you" and then leave board_actions empty — that is WRONG.

POSITIONING: Always use x=20, y=140 as your starting position. Space lines ~60px apart vertically.
The system places your content below existing writing automatically — do NOT offset y yourself based on previous turns.

Colors: #000000 = working through it, #0000FF = hints/new content, #FF0000 = corrections, #00AA00 = correct answers

--- EXAMPLES ---

Linked list:
board_actions = [
  {"type":"write","content":"[1] -> [2] -> [3] -> null","position":{"x":20,"y":140},"color":"#000000"}
]

Reversing a linked list:
board_actions = [
  {"type":"write","content":"Before: [1]->[2]->[3]->null","position":{"x":20,"y":140},"color":"#000000"},
  {"type":"write","content":"After:  [3]->[2]->[1]->null","position":{"x":20,"y":200},"color":"#0000FF"},
  {"type":"write","content":"prev=null  curr=head  next=curr.next","position":{"x":20,"y":280},"color":"#FF0000"}
]

Algorithm steps:
board_actions = [
  {"type":"write","content":"1. prev = null,  curr = head","position":{"x":20,"y":140},"color":"#000000"},
  {"type":"write","content":"2. next = curr.next","position":{"x":20,"y":200},"color":"#000000"},
  {"type":"write","content":"3. curr.next = prev","position":{"x":20,"y":260},"color":"#000000"},
  {"type":"write","content":"4. prev = curr,  curr = next","position":{"x":20,"y":320},"color":"#000000"}
]

Math equation:
board_actions = [
  {"type":"write","content":"x^2 + 2x + 1 = 0","position":{"x":20,"y":140},"color":"#000000"},
  {"type":"write","content":"(x + 1)^2 = 0","position":{"x":20,"y":200},"color":"#0000FF"},
  {"type":"write","content":"x = -1","position":{"x":20,"y":260},"color":"#00AA00"}
]

Hint mid-conversation (student is stuck):
board_actions = [
  {"type":"write","content":"Hint: what does curr.next point to before you move curr?","position":{"x":20,"y":140},"color":"#0000FF"}
]

--- END EXAMPLES ---

RULES:
- type: "write" (draw text) or "clear" (wipe the whole board — use sparingly)
- format: "text" (default) or "latex" for equations/symbol-heavy math
- content: plain string for format="text"; valid LaTeX for format="latex"
- position: {"x": number, "y": number} — always x=20, y=140
- color: hex string

When you see a whiteboard image, acknowledge what the student drew before moving on.

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
