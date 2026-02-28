# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**AI Tutor with Interactive Freehand Whiteboard** — a voice-first tutoring app where a student talks to an AI professor ("Professor Ada") while sharing a freehand whiteboard. The AI sees the student's handwriting via vision, speaks back via TTS, and writes on the board with animated handwriting strokes.

The spec lives in `Professor.Md`. No code has been written yet.

---

## Target Repository Structure

```
ai-tutor/
├── frontend/          # React + TypeScript + Vite
└── backend/           # Python + FastAPI
```

---

## Quick Start Commands (once code exists)

```bash
# Backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in API keys
uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

---

## Tech Stack

**Frontend:** React + TypeScript (Vite), tldraw (whiteboard), shadcn/ui + Tailwind CSS, Zustand (state), Web Audio API

**Backend:** FastAPI (Python), WebSockets

**AI Services:**
- LLM + Vision: Claude API (`claude-sonnet-4-5`) — text + vision calls
- STT: Deepgram Nova-2 (streaming WebSocket)
- TTS: ElevenLabs (streaming audio chunks)
- Handwriting synthesis: `sjvasquez/handwriting-synthesis` (Python/TensorFlow)

---

## Architecture

The frontend communicates with the backend via a single WebSocket. The backend orchestrator routes between four subsystems:

```
Frontend WebSocket ──► Orchestrator (orchestrator.py)
                            ├── llm_client.py      → Claude API (text + vision)
                            ├── tts_client.py      → ElevenLabs streaming
                            ├── stt_client.py      → Deepgram proxy
                            └── handwriting/
                                ├── synthesizer.py      (text → strokes)
                                └── latex_to_strokes.py (LaTeX → SVG → strokes)
```

**Session state** (`session.py`) tracks: `conversation_history`, `current_subject`, `tutor_mode` (listening/guiding/demonstrating/evaluating), `board_snapshots`, `student_progress`.

---

## Critical Data Formats

### LLM Response (structured JSON the backend parses)
```json
{
  "speech": "...",
  "board_actions": [
    { "type": "write", "content": "...", "format": "text|latex", "position": {"x": 0, "y": 0}, "color": "#FF0000" },
    { "type": "underline", "target_area": {"x": 0, "y": 0, "width": 0, "height": 0}, "color": "#FF0000" }
  ],
  "tutor_state": "guiding",
  "wait_for_student": false
}
```

### Stroke Data (universal format for both text and LaTeX paths)
```json
{
  "strokes": [
    { "points": [{"x": 0, "y": 0, "pressure": 0.8}], "color": "#FF0000", "width": 2 }
  ],
  "position": {"x": 0, "y": 0},
  "animation_speed": 1.0
}
```

---

## Handwriting Synthesis Pipelines

**Plain text:** `sjvasquez/handwriting-synthesis` model → `(x, y, end_of_stroke)` tuples → frontend animates with `requestAnimationFrame` + ±1px jitter for organic feel.

**LaTeX/math:** LaTeX → MathJax server-side SVG → extract `<path d="...">` elements → sample points with `svgpathtools` (Python) or `svg-path-properties` (npm) → same stroke format as above.

The frontend `strokeAnimator.ts` handles both formats identically.

---

## Whiteboard Snapshot Triggers

Board screenshots are sent to the LLM as vision inputs. Trigger on: 2-3s drawing pause, voice keywords ("take a look"), or manual button. Periodic snapshots (every 5-10s) are low priority.

---

## AI Persona & System Prompt

The AI is "Professor Ada" — warm, Socratic, uses natural speech. Key behaviors:
- Ask guiding questions before giving answers
- Red ink = corrections, blue = hints, green = correct work
- Narrate whiteboard actions out loud as they happen
- Respond only in the structured JSON format above

---

## Required API Keys (.env)

| Key | Service |
|-----|---------|
| `ANTHROPIC_API_KEY` | Claude API (LLM + vision) |
| `DEEPGRAM_API_KEY` | Speech-to-text |
| `ELEVENLABS_API_KEY` | Text-to-speech |

---

## MVP Priorities

1. Voice pipeline end-to-end (STT → LLM → TTS)
2. Freehand whiteboard (tldraw) with canvas snapshot export
3. AI vision reading the board
4. AI animated handwriting on the board (text strokes first, LaTeX second)
5. Session flow: greeting → topic → problem solving → feedback
