# Professor

Voice-first AI tutoring app with a shared whiteboard.  
The student speaks and draws, and the AI tutor (`Professor KIA`) responds with speech plus animated handwritten strokes.

## Features

- Live voice conversation over WebSocket
- Streaming STT with Deepgram
- Streaming TTS with ElevenLabs
- LLM reasoning + whiteboard vision with Anthropic
- Animated AI handwriting (font-driven stroke synthesis)
- LaTeX-to-strokes pipeline via local MathJax renderer
- Interrupt / barge-in behavior during AI speech

## Tech Stack

- Frontend: Next.js 14, TypeScript, Tailwind, Zustand, tldraw
- Backend: FastAPI, asyncio WebSockets
- AI services: Anthropic, Deepgram, ElevenLabs
- Rendering: `fonttools`, `svgpathtools`

## Repo Structure

```text
backend/
  app/
    main.py
    orchestrator.py
    llm_client.py
    stt_client.py
    tts_client.py
    handwriting/
      synthesizer.py
      latex_to_strokes.py
  latex_renderer/
frontend/
docker-compose.yml
.env.example
```

## Prerequisites

- Python 3.11+
- Node.js 20+
- `pnpm`
- Docker + Docker Compose (optional, recommended)

## Environment Setup

1. Copy env file:
```bash
cp .env.example .env
```
2. Fill required API keys in `.env`:
- `ANTHROPIC_API_KEY`
- `DEEPGRAM_API_KEY`
- `ELEVENLABS_API_KEY`

Optional but useful:
- `ELEVENLABS_VOICE_ID`
- `DEEPGRAM_MODEL`
- `DEEPGRAM_ENDPOINTING_MS`
- `BOARD_WRITE_X`
- `LATEX_TARGET_HEIGHT_*`

## Run With Docker (Recommended)

From repo root:

```bash
docker compose up --build
```

Services:
- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000` (`/health`)
- LaTeX renderer: `http://localhost:3001/mathjax`

## Run Locally (Without Docker)

### 1) Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 2) LaTeX Renderer

```bash
cd backend/latex_renderer
npm install
npm run start
```

### 3) Frontend

```bash
cd frontend
pnpm install
pnpm dev
```

## Useful Commands

```bash
# Frontend type-check
pnpm -C frontend typecheck

# Frontend build
pnpm -C frontend build

# Backend quick compile check
python3 -m compileall backend/app
```

## WebSocket Endpoint

- URL: `ws://localhost:8000/ws/{session_id}`
- Health check: `GET /health`

## Notes

- AI handwriting and student drawing are handled separately for better UX and control.
- Whiteboard placement is cursor-managed server-side to reduce AI overlap.
- Snapshot payloads used for vision are filtered to avoid AI reading its own overlay strokes.

## Troubleshooting

- If speech cuts off too early, increase:
  - `DEEPGRAM_ENDPOINTING_MS`
  - `STT_MERGE_WINDOW_SEC`
- If AI writing starts too far right/left, tune:
  - `BOARD_WRITE_X`
- If Docker build fails with snapshot/caching errors:
  - `docker builder prune -af`
  - then rerun `docker compose up --build`

