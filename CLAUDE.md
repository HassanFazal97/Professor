# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**AI Tutor with Interactive Freehand Whiteboard** — a voice-first tutoring app where a student talks to an AI professor ("Professor KIA") while sharing a freehand whiteboard. The AI sees the student's handwriting via vision, speaks back via TTS, and writes on the board with animated handwriting strokes using a Patrick Hand font synthesis pipeline.

The full spec lives in `Professor.Md`.

---

## Quick Start Commands

```bash
# Backend
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in API keys
uvicorn app.main:app --reload --port 8000

# LaTeX renderer (separate terminal)
cd backend/latex_renderer
npm install
npm run start

# Frontend (separate terminal)
cd frontend
pnpm install
pnpm dev

# Type-check frontend
cd frontend && pnpm typecheck

# Docker Compose (frontend + backend + latex-renderer)
cd ..
docker compose up --build
```

---

## Tech Stack

**Frontend:** Next.js 14 (App Router), TypeScript, pnpm, tldraw v2.4.6 (whiteboard), Zustand (state), Tailwind CSS, Web Audio API

**Backend:** FastAPI (Python 3.11+), asyncio WebSockets

**AI Services:**
- LLM + Vision: Claude API (`claude-haiku-4-5-20251001`) — structured JSON responses, streaming
- STT: Deepgram Nova-2 (streaming WebSocket proxy, webm/opus encoding, VAD barge-in events)
- TTS: ElevenLabs `eleven_v3` (streaming raw PCM `pcm_22050` — 22050 Hz, 16-bit signed LE, mono); voice configurable via `ELEVENLABS_VOICE_ID` env var (default: `pNInz6obpgDQGcFmaJgB` / Adam)
- Handwriting: `PatrickHand-Regular.ttf` (Google Fonts, OFL) via `fonttools` — glyph Bézier curves → stroke points. Font auto-downloads to `backend/app/handwriting/PatrickHand-Regular.ttf` on first run.

---

## Architecture

Frontend connects to backend via a **single WebSocket** at `ws://localhost:8000/ws/{session_id}`. All messages are JSON with a `type` discriminator.

```
Frontend WebSocket ──► Orchestrator (orchestrator.py)
                            ├── llm_client.py      → Claude API (text + vision, streams JSON)
                            ├── tts_client.py      → ElevenLabs streaming PCM audio
                            ├── stt_client.py      → Deepgram STT WebSocket proxy
                            └── handwriting/
                                ├── synthesizer.py      (text → strokes via Patrick Hand font)
                                └── latex_to_strokes.py (LaTeX → MathJax SVG → stroke points)
```

**Session state** (`session.py`): `conversation_history`, `current_subject`, `tutor_mode`, `board_snapshots`, `board_next_y` / `board_viewport_y` / `student_content_bottom_y` (track y-cursors for non-overlapping writes), `board_width`, `board_height`.

---

## Implementation Status

**All core systems are fully implemented — nothing is stubbed:**

| Component | File | Status |
|-----------|------|--------|
| LLM client | `backend/app/llm_client.py` | ✅ Streaming JSON, vision attachment, early speech extraction |
| TTS client | `backend/app/tts_client.py` | ✅ ElevenLabs `pcm_22050` streaming via aiohttp |
| STT client | `backend/app/stt_client.py` | ✅ Deepgram Nova-2 WebSocket, barge-in, KeepAlive, confidence filter |
| Orchestrator | `backend/app/orchestrator.py` | ✅ Full barge-in, rebasing, scroll, proactive review, STT merge |
| Handwriting | `backend/app/handwriting/synthesizer.py` | ✅ Patrick Hand font, superscript `^`, pressure curves |
| LaTeX | `backend/app/handwriting/latex_to_strokes.py` | ✅ MathJax SVG → path sampling → strokes; fallback to font synthesizer |
| Voice pipeline | `frontend/src/hooks/useVoicePipeline.ts` | ✅ MediaRecorder webm/opus, echoCancellation, streams to backend |
| Audio player | `frontend/src/lib/audioPlayer.ts` | ✅ PCM 22050 Hz queue, barge-in stop, `onDrained` callback |
| Whiteboard | `frontend/src/components/Whiteboard.tsx` | ✅ tldraw + composite snapshot (student-only export) |
| Overlay | `frontend/src/components/WhiteboardOverlay.tsx` | ✅ Canvas RAF animation, world→screen via `editor.pageToScreen` |

**What still needs work:**
- Session persistence (in-memory only; sessions lost on backend restart)
- Mobile / touch layout (tldraw works on touch but UI is desktop-optimised)
- Subject-specific curricula and student progress tracking

---

## WebSocket Message Protocol

**Client → Server:**
| `type` | Fields | Description |
|--------|--------|-------------|
| `session_start` | `subject` | Begins session, triggers greeting |
| `transcript` | `text` | Final STT transcript (also sent by STT flush via `transcript_interim`) |
| `board_snapshot` | `image_base64`, `width?`, `height?`, `student_max_y?` | PNG of student-only whiteboard |
| `audio_start` | — | Open Deepgram STT session on backend |
| `audio_data` | `data` (base64 webm/opus chunk) | Streaming mic audio |
| `audio_stop` | — | Signal end-of-stream; triggers final transcript flush |
| `barge_in` | — | Student started speaking; interrupt Ada immediately |

**Server → Client:**
| `type` | Fields | Description |
|--------|--------|-------------|
| `connected` | `session_id`, `message` | Sent on WebSocket connect |
| `speech_text` | `text` | Ada's full speech text (fires as soon as JSON speech field is complete) |
| `audio_chunk` | `data` (base64 raw PCM) | Streaming TTS audio; frontend decodes 16-bit LE at 22050 Hz |
| `strokes` | `strokes: StrokeData` | Animated handwriting strokes batch |
| `board_action` | `action: BoardAction` | Non-write board action (underline, clear) |
| `transcript_interim` | `text` | Merged STT utterance — triggers LLM call and updates UI |
| `state_update` | `tutor_state`, `wait_for_student` | Ada state change |
| `scroll_board` | `scroll_by` | Pan tldraw camera down by `scroll_by` px |
| `snapshot_received` | `count` | Backend ACK for board snapshot (not in frontend type union; silently dropped) |
| `error` | `message` | Server-side error |

Note: there is **no `audio_done` message**. TTS end is detected on the frontend when `audioPlayer.onDrained` fires (queue empties naturally).

---

## Critical Data Formats

### LLM Response (structured JSON — no markdown fences)
```json
{
  "speech": "...",
  "board_actions": [
    { "type": "write", "content": "x^2 + 1", "format": "text", "position": {"x": 0, "y": 140}, "color": "#0000FF" },
    { "type": "write", "content": "\\frac{1}{2}", "format": "latex", "position": {"x": 0, "y": 200}, "color": "#000000" },
    { "type": "underline", "target_area": {"x": 0, "y": 140, "width": 100, "height": 20}, "color": "#FF0000" },
    { "type": "clear" }
  ],
  "tutor_state": "listening",
  "wait_for_student": false
}
```

`format` on a `write` action is `"text"` (default, rendered via Patrick Hand font) or `"latex"` (rendered via MathJax → SVG → strokes). `underline` draws a thin rectangle below a target area.

### Stroke Data (sent as `{ type: "strokes", strokes: StrokeData }`)
```json
{
  "strokes": [
    { "points": [{"x": 100, "y": 200, "pressure": 0.8}], "color": "#000000", "width": 1.5 }
  ],
  "position": {"x": 20, "y": 140},
  "animation_speed": 1.0
}
```

`animation_speed` calibrated by orchestrator so all writing finishes in roughly the same time as Ada's speech (~2.4 words/sec). Frontend draws `Math.round(speed * DEFAULT_SPEED * 2)` points per RAF frame where `DEFAULT_SPEED = 2.0`.

---

## Key Architectural Patterns

### Board Position Rebasing (`orchestrator.py`)
The LLM always writes at `x=0, y=140`. `_rebase_board_actions()` translates coordinates to world space, applying `BOARD_WRITE_X` (default `20`) as the actual x-offset, placing new content below both Ada's prior cursor (`board_next_y`) and the student's shapes (`student_content_bottom_y`). When content won't fit in the current viewport, a `scroll_board` sentinel is **prepended** (not `clear`) so the camera pans down to reveal fresh space. `_normalize_board_actions()` runs first to word-wrap long lines based on board width.

### Board Cursor Tracking
After each response, `_update_board_cursor()` reads the actual rendered stroke bottom-y (from `_stroke_payload_bottom_y()`) to advance `board_next_y` accurately. This uses real stroke points rather than fixed estimates.

### Barge-In / Interrupt (two-phase)
1. Deepgram fires `SpeechStarted` (VAD event, before transcript) → backend records `_pending_auto_barge_at`
2. A real final transcript arrives confirming speech → backend calls `_emit_barge_in()` which sends `{ type: "barge_in" }` and sets `_interrupted = True`
3. `_dispatch_llm_response` checks `_interrupted` before each stroke/audio chunk and stops early
4. Manual `{ type: "barge_in" }` from frontend (e.g. button press) skips step 1–2
5. Frontend: `audioPlayer.stop()` cuts audio instantly; `cancelStrokes()` sets `pendingStrokes → null`; `cancelRef` in `WhiteboardOverlay` stops the RAF loop

Guards: `_barge_start_guard_sec` (0.25s) ignores `SpeechStarted` right after TTS starts; `_auto_barge_debounce_sec` (0.5s) prevents rapid re-barge; `_echo_cooldown` (1.2s) suppresses transcripts that are likely Ada's own voice echoing back.

### STT Utterance Merging
Deepgram can emit multiple final chunks for one utterance. `_on_stt_transcript` buffers chunks into `_stt_buffer` and schedules a `_flush_stt_buffer_after_delay` task (`STT_MERGE_WINDOW_SEC` = 0.8s). New chunks reset the timer. This ensures Ada responds to the complete thought.

### Proactive Board Analysis
When `wait_for_student = True` and the student has been silent for 6s with no analysis in 15s, `_handle_board_snapshot` schedules `_proactive_board_analysis`. Ada reviews the board snapshot and marks mistakes in red. A synthetic `"[checking my work on the board]"` turn is added inside the `_llm_lock`; removed silently if LLM returns nothing.

### Composite Snapshot
`Whiteboard.tsx` exports only student shapes (filtering out `meta.createdBy === "ai-tutor"`) via tldraw's `exportToBlob`. The tldraw camera is locked at `{x:0, y:0, z:0.8}` so overlay canvas pixel coordinates align with page coordinates. `WhiteboardOverlay` uses `editor.pageToScreen()` to convert world-space stroke points to screen pixels when drawing.

### Audio Pipeline
`audioPlayer.ts` decodes raw 16-bit signed LE PCM at 22050 Hz directly (no MP3 decoder latency). Chunks are scheduled on `AudioContext` wall-clock time so playback is gapless across chunks. `onDrained` fires when all `AudioBufferSourceNode`s have ended naturally, clearing `adaSpeaking` in `useTutorSession`.

### LLM Response Streaming
`llm_client.py` streams the Claude response and parses the `"speech"` field as soon as its closing `"` arrives in the accumulated string (using `_try_extract_speech()`). `on_speech_ready(text)` is called immediately so TTS synthesis starts while the rest of the JSON (board_actions) continues to arrive — minimising first-audio latency.

---

## Frontend State (Zustand)

- **`useTutorSession`** (`hooks/useTutorSession.ts`): WebSocket lifecycle, `adaSpeaking` flag, `waitForStudent`, `conversationHistory`, all `ServerMessage` dispatch
- **`useWhiteboard`** (`hooks/useWhiteboard.ts`): `pendingStrokes` / `strokeQueue` animation pipeline, `pendingBoardActions` queue, `overlayCanvas` ref, `cancelStrokes()`, `scrollBoard()`, `clearOverlay()`
- **`useVoicePipeline`** (`hooks/useVoicePipeline.ts`): MediaRecorder (webm/opus, 250ms chunks), mic stream lifecycle, echoCancellation + noiseSuppression + autoGainControl

---

## Important Config Notes

- `reactStrictMode: false` in `next.config.js` — required to prevent double canvas mount with tldraw
- `transpilePackages: ["@tldraw/tldraw", "@tldraw/editor"]` in `next.config.js`
- All components using browser APIs must have `"use client"` at top
- tldraw API: `exportToBlob({ editor, ids, format, opts })` — NOT `editor.toImage()`
- Backend uses `python3` (not `python`) on macOS
- Pylance shows "anthropic import not resolved" in editor — it reads system Python, not the venv. Harmless.

---

## Required API Keys (.env)

| Key | Service |
|-----|---------|
| `ANTHROPIC_API_KEY` | Claude API (LLM + vision) |
| `DEEPGRAM_API_KEY` | Speech-to-text |
| `ELEVENLABS_API_KEY` | Text-to-speech |
| `ELEVENLABS_VOICE_ID` | *(optional)* Override TTS voice (default: `pNInz6obpgDQGcFmaJgB` / Adam) |
| `LLM_MODEL` | *(optional)* Override LLM model (default: `claude-haiku-4-5-20251001`; use `claude-sonnet-4-6` for best quality) |
| `FRONTEND_URL` | *(optional)* CORS allowed origin (default: `http://localhost:3000`) |
| `BACKEND_PORT` | *(optional)* Backend listen port (default: `8000`) |
| `LATEX_RENDER_URL` | *(optional)* MathJax renderer endpoint (default: `http://localhost:3001/mathjax`) |
| `LATEX_TARGET_HEIGHT_PX` | *(optional)* Base visual height for LaTeX strokes in px (default: `70`) |
| `LATEX_TARGET_HEIGHT_MIN_PX` | *(optional)* Minimum adaptive LaTeX height (default: `54`) |
| `LATEX_TARGET_HEIGHT_MAX_PX` | *(optional)* Maximum adaptive LaTeX height (default: `110`) |
| `BOARD_WRITE_X` | *(optional)* X-origin for Ada's board writes (default: `20`) |
| `ECHO_COOLDOWN_SEC` | *(optional)* Suppress STT transcripts for N sec after TTS sent (default: `1.2`) |
| `AUTO_BARGE_DEBOUNCE_SEC` | *(optional)* Min interval between auto barge-ins (default: `0.5`) |
| `BARGE_START_GUARD_SEC` | *(optional)* Ignore SpeechStarted within N sec of TTS start (default: `0.25`) |
| `AUTO_BARGE_CONFIRM_WINDOW_SEC` | *(optional)* Max age of pending barge to be confirmed by transcript (default: `1.5`) |
| `STT_MERGE_WINDOW_SEC` | *(optional)* Buffer window to merge adjacent STT finals (default: `0.8`) |
| `STT_FINAL_AFTER_CLOSE_WAIT_SEC` | *(optional)* Wait for final transcript after CloseStream (default: `2.5`) |
| `DEEPGRAM_ENDPOINTING_MS` | *(optional)* STT end-of-utterance timeout (default: `300`) |
| `DEEPGRAM_MODEL` | *(optional)* Deepgram model (default: `nova-2`) |
| `STT_MIN_CONFIDENCE` | *(optional)* Minimum transcript confidence (default: `0.50`) |
| `STT_SINGLE_WORD_MIN_CONFIDENCE` | *(optional)* Single-word confidence threshold (default: `0.70`) |
| `STT_MIN_WORDS` | *(optional)* Minimum word count for a transcript to be processed (default: `1`) |
