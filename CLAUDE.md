# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**AI Tutor with Interactive Freehand Whiteboard** — a voice-first tutoring app where a student talks to an AI professor ("Professor Ada") while sharing a freehand whiteboard. The AI sees the student's handwriting via vision, speaks back via TTS, and writes on the board with animated handwriting strokes using a Caveat font synthesis pipeline.

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

**Frontend:** Next.js 14 (App Router), TypeScript, pnpm, tldraw (whiteboard), Zustand (state), Tailwind CSS, Web Audio API

**Backend:** FastAPI (Python 3.11+), asyncio WebSockets

**AI Services:**
- LLM + Vision: Claude API (`claude-haiku-4-5-20251001`) — structured JSON responses
- STT: Deepgram Nova-2 (streaming WebSocket proxy)
- TTS: ElevenLabs `eleven_flash_v2_5` (streaming audio chunks); voice configurable via `ELEVENLABS_VOICE_ID` env var (default: Rachel)
- Handwriting: Caveat-Regular.ttf via `fonttools` — glyph Bézier curves → stroke points. Font auto-downloads to `backend/app/handwriting/Caveat-Regular.ttf` on first run.

---

## Architecture

Frontend connects to backend via a **single WebSocket** at `ws://localhost:8000/ws/{session_id}`. All messages are JSON with a `type` discriminator.

```
Frontend WebSocket ──► Orchestrator (orchestrator.py)
                            ├── llm_client.py      → Claude API (text + vision, streams JSON)
                            ├── tts_client.py      → ElevenLabs streaming audio
                            ├── stt_client.py      → Deepgram STT proxy
                            └── handwriting/
                                ├── synthesizer.py      (text → strokes via Caveat font)
                                └── latex_to_strokes.py (LaTeX SVG paths → strokes)
```

**Session state** (`session.py`): `conversation_history`, `current_subject`, `tutor_mode`, `board_snapshots`, `board_next_y` (tracks y-cursor for non-overlapping writes).

---

## WebSocket Message Protocol

**Client → Server:**
| `type` | Fields | Description |
|--------|--------|-------------|
| `session_start` | `subject` | Begins session, triggers greeting |
| `transcript` | `text` | Final STT transcript |
| `board_snapshot` | `image_base64` | PNG of composite whiteboard |
| `barge_in` | — | Student started speaking; interrupt Ada |

**Server → Client:**
| `type` | Fields | Description |
|--------|--------|-------------|
| `speech_text` | `text` | Ada's speech text (fires before audio) |
| `audio_chunk` | `data` (base64 PCM) | Streaming TTS audio |
| `audio_done` | — | TTS stream finished |
| `strokes` | `StrokeData` | Animated handwriting strokes |
| `error` | `message` | Server-side error |

---

## Critical Data Formats

### LLM Response (structured JSON — no markdown fences)
```json
{
  "speech": "...",
  "board_actions": [
    { "type": "write", "content": "x^2 + 1", "position": {"x": 80, "y": 140}, "color": "#0000FF" },
    { "type": "clear" }
  ],
  "tutor_state": "listening",
  "wait_for_student": false
}
```

### Stroke Data (sent as `{ type: "strokes", ... }` over WebSocket)
```json
{
  "strokes": [
    { "points": [{"x": 100, "y": 200, "pressure": 0.8}], "color": "#000000", "width": 1.5 }
  ],
  "animation_speed": 1.0
}
```

---

## Key Architectural Patterns

### Board Position Rebasing (orchestrator.py)
The LLM always writes starting at `x=80, y=140`. The orchestrator's `_rebase_board_actions()` shifts all write-action y-coordinates so content starts below the existing `board_next_y`. If content would exceed y=600, a `clear` action is prepended and the cursor resets. This prevents overlapping without relying on LLM instruction-following.

### Barge-In / Interrupt
When the student starts speaking:
1. Frontend sends `{ type: "barge_in" }` over WebSocket
2. Backend sets `_interrupted = True` — `_dispatch_llm_response` drops remaining audio/strokes
3. `asyncio.Lock (_llm_lock)` serializes all LLM calls; `_on_stt_transcript` uses `create_task` so the STT recv loop never blocks on LLM work
4. Frontend: `audioPlayer.stop()` calls `AudioBufferSourceNode.stop()` immediately; `cancelStrokes()` sets `pendingStrokes → null`, triggering `cancelRef` in `WhiteboardOverlay`

### Proactive Board Analysis
When a student draws silently (no speech for 4s, no analysis for 15s), `_handle_board_snapshot` schedules `_proactive_board_analysis`. Ada reviews the board snapshot and corrects mistakes in red. A synthetic `"[checking my work on the board]"` turn is added to conversation history inside the lock; removed if LLM returns empty response.

### Composite Snapshot
`Whiteboard.tsx` composites tldraw's `exportToBlob` (student strokes) with the `WhiteboardOverlay` canvas (Ada's animated handwriting) into a single PNG sent to the LLM for vision. The tldraw camera is locked at `{x:0, y:0, z:1}` so overlay coordinates align with page coordinates.

### Audio Queue & `adaSpeaking` State
`audioPlayer.ts` maintains a buffer queue. `onDrained` fires when the queue empties naturally, clearing `adaSpeaking` in `useTutorSession`. STT audio now streams continuously (including while Ada speaks) so Deepgram can detect speak-over barge-ins in real time; backend echo/barge filters suppress false triggers.

---

## Frontend State (Zustand)

- **`useTutorSession`**: WebSocket connection, session lifecycle, `adaSpeaking` flag, barge-in handler
- **`useWhiteboard`**: `pendingStrokes` / `strokeQueue` animation pipeline, `overlayCanvas` ref, `cancelStrokes()`
- **`useVoicePipeline`**: Deepgram STT MediaRecorder, VAD silence detection, transcript dispatch

---

## Important Config Notes

- `reactStrictMode: false` in `next.config.js` — required to prevent double canvas mount issues with tldraw
- `transpilePackages: ["@tldraw/tldraw", "@tldraw/editor"]` in `next.config.js`
- All components using browser APIs must have `"use client"` at top
- LaTeX handwriting pipeline (`latex_to_strokes.py`) is **fully stubbed** — returns placeholder strokes

---

## Required API Keys (.env)

| Key | Service |
|-----|---------|
| `ANTHROPIC_API_KEY` | Claude API (LLM + vision) |
| `DEEPGRAM_API_KEY` | Speech-to-text |
| `ELEVENLABS_API_KEY` | Text-to-speech |
| `ELEVENLABS_VOICE_ID` | *(optional)* Override TTS voice (default: Rachel) |
| `LLM_MODEL` | *(optional)* Override LLM model (default: `claude-haiku-4-5-20251001`, use `claude-sonnet-4-5` for demo quality) |
| `LATEX_RENDER_URL` | *(optional)* Local LaTeX SVG renderer URL (default: `http://localhost:3001/mathjax`) |
| `ECHO_COOLDOWN_SEC` | *(optional)* Echo suppression window for STT transcripts |
| `AUTO_BARGE_DEBOUNCE_SEC` | *(optional)* Min interval between auto barge-ins |
| `BARGE_START_GUARD_SEC` | *(optional)* Ignore SpeechStarted right after TTS begins |
| `AUTO_BARGE_CONFIRM_WINDOW_SEC` | *(optional)* Max delay to confirm SpeechStarted with a transcript |
