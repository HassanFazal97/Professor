# AI Tutor with Interactive Freehand Whiteboard

## Project Overview

An AI-powered tutoring web application that simulates a one-on-one session with a real professor. The app combines real-time voice conversation with a shared freehand whiteboard where both the student and the AI can draw, write, and annotate. The AI tutor speaks naturally, asks Socratic questions, watches what the student writes on the board, and can take over the whiteboard to write hints, corrections, or work through problems — all with realistic handwriting animation.

---

## What Makes This Different

Existing AI tutors (like TutorFlow AI, Khanmigo, etc.) are text-based chat interfaces with structured content. This project is different because:

- **Voice-first interaction** — feels like talking to a real professor, not typing into a chatbot
- **Shared freehand whiteboard** — both the user and AI draw/write freely, not just render LaTeX or structured content
- **AI "sees" your handwriting** — the AI interprets what you've written on the board using vision, then responds contextually
- **AI writes back with realistic handwriting** — not rendered text, but animated strokes that look hand-drawn
- **Real-time feedback loop** — the AI can interrupt ("Wait, check your sign there") or take over the board mid-problem

---

## Core User Flow

1. Student opens the app → sees a split screen: AI tutor video/avatar on one side, whiteboard on the other
2. AI greets them vocally: "Hey, what brings you in today?"
3. Student speaks: "I'm struggling with integration by parts for my calc midterm"
4. AI responds conversationally, asks where they're stuck, suggests working through a problem
5. Student writes a practice problem on the whiteboard (freehand, with mouse or stylus)
6. AI "sees" the board via periodic canvas screenshots → vision model interprets the math
7. AI says "Okay, walk me through it" — student begins solving on the board
8. If the student makes an error, the AI pauses them vocally and highlights the issue
9. AI can take over the board — writes hints, corrections, or partial solutions with animated handwriting
10. Back and forth continues naturally until the student understands the concept

---

## Tech Stack

### Frontend — React + TypeScript

| Component | Library | Purpose |
|-----------|---------|---------|
| **Framework** | React (Vite or Next.js) | Main app shell |
| **Whiteboard** | tldraw or Excalidraw | Freehand drawing canvas with good pen/stylus support |
| **Handwriting rendering** | Custom canvas animation layer | Animates AI stroke data onto the whiteboard |
| **UI components** | shadcn/ui + Tailwind CSS | Clean, minimal interface |
| **Audio handling** | Web Audio API | Mic input capture, audio playback |
| **State management** | Zustand or React Context | Manage whiteboard state, conversation state, AI mode |

### Backend — Node.js (Express) or Python (FastAPI)

| Component | Library / Service | Purpose |
|-----------|-------------------|---------|
| **Server framework** | FastAPI (Python) recommended | Handles API routing, WebSocket connections |
| **WebSocket server** | FastAPI WebSockets or Socket.IO | Real-time communication between frontend and AI pipeline |
| **Handwriting synthesis** | sjvasquez/handwriting-synthesis (Python, TensorFlow) | Converts AI text output to realistic stroke coordinate data |
| **LaTeX → SVG → Strokes** | MathJax (server-side) + svg-path-properties | For math notation: render LaTeX to SVG, extract paths, convert to animatable stroke data |
| **Canvas processing** | Pillow / Sharp | Process whiteboard screenshots before sending to vision model |

### AI / ML Services

| Component | Service | Purpose |
|-----------|---------|---------|
| **Conversational AI** | Claude API (claude-sonnet-4-5) or GPT-4o | Main "brain" — handles conversation, pedagogy, decides what to write on board |
| **Vision / Whiteboard reading** | Claude (vision) or GPT-4o (vision) | Interprets freehand math/text from canvas screenshots |
| **Speech-to-Text** | Deepgram (Nova-2) | Real-time transcription of student speech. Low latency, good accuracy. |
| **Text-to-Speech** | ElevenLabs or OpenAI TTS | Professor voice. ElevenLabs for more natural/customizable voice. |

### Infrastructure

| Component | Service | Purpose |
|-----------|---------|---------|
| **Hosting** | Vercel (frontend) + Railway or Fly.io (backend) | Quick deploy for hackathon |
| **Environment** | Docker (optional) | Package the handwriting synthesis model |
| **Secrets management** | .env files | API keys for Deepgram, ElevenLabs, Claude/OpenAI |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        FRONTEND (React)                     │
│                                                             │
│  ┌──────────────┐  ┌────────────────────────────────────┐   │
│  │  AI Tutor    │  │  Shared Whiteboard (tldraw)        │   │
│  │  Panel       │  │                                    │   │
│  │              │  │  - User freehand drawing layer     │   │
│  │  - Avatar/   │  │  - AI handwriting animation layer  │   │
│  │    waveform  │  │  - Tool palette (pen, eraser,      │   │
│  │  - Status    │  │    colors, clear)                  │   │
│  │    indicator │  │  - Snapshot trigger                 │   │
│  │  - Captions  │  │                                    │   │
│  │    (optional)│  │                                    │   │
│  └──────────────┘  └────────────────────────────────────┘   │
│                                                             │
│  Mic Input (Web Audio API) ──► Deepgram STT (WebSocket)     │
│  Speaker Output ◄── Audio chunks from TTS                   │
└──────────────────────┬──────────────────────────────────────┘
                       │ WebSocket
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                     BACKEND (FastAPI)                        │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Orchestrator / Session Manager          │    │
│  │                                                     │    │
│  │  - Receives: transcribed speech + board snapshots   │    │
│  │  - Maintains: conversation history + board state    │    │
│  │  - Sends to: LLM with multimodal context            │    │
│  │  - Receives from LLM: speech text + board actions   │    │
│  │  - Routes: speech text → TTS, board actions →       │    │
│  │    handwriting synthesis                             │    │
│  └──────────┬──────────────┬───────────────┬───────────┘    │
│             │              │               │                │
│     ┌───────▼──────┐ ┌────▼─────┐ ┌───────▼──────────┐     │
│     │  LLM API     │ │  TTS     │ │  Handwriting     │     │
│     │  (Claude /   │ │  (Eleven │ │  Synthesis       │     │
│     │   GPT-4o)    │ │   Labs)  │ │  Engine          │     │
│     │              │ │          │ │                   │     │
│     │  - Text +    │ │  Returns │ │  - Text → strokes │     │
│     │    vision    │ │  audio   │ │  - LaTeX → SVG →  │     │
│     │  - Returns   │ │  chunks  │ │    strokes        │     │
│     │    structured│ │          │ │  - Returns [{x,y, │     │
│     │    response  │ │          │ │    pressure, t}]  │     │
│     └──────────────┘ └──────────┘ └───────────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

---

## Key Implementation Details

### 1. AI Response Format

The LLM should return structured JSON so the backend can route speech and board actions separately:

```json
{
  "speech": "Hmm, let me take a look at what you wrote. I see you set up the integral correctly, but watch your u-substitution — let me write something on the board.",
  "board_actions": [
    {
      "type": "write",
      "content": "Let u = x^2, then du = 2x dx",
      "format": "text",
      "position": { "x": 400, "y": 200 },
      "color": "#FF0000"
    },
    {
      "type": "underline",
      "target_area": { "x": 100, "y": 150, "width": 300, "height": 50 },
      "color": "#FF0000"
    }
  ],
  "tutor_state": "guiding",
  "wait_for_student": false
}
```

### 2. Handwriting Synthesis Pipeline (Option C)

**For plain text and code (English characters):**

```
AI output text → sjvasquez/handwriting-synthesis model → stroke coordinates
→ send to frontend → animate on canvas with requestAnimationFrame
```

The handwriting-synthesis model outputs sequences of (x, y, end_of_stroke) tuples. Your frontend iterates through these points, drawing line segments with a slight delay between each to simulate real-time writing. Add a small random jitter (±1px) for organic feel.

**For math notation (LaTeX):**

```
AI output LaTeX → MathJax server-side render → SVG output
→ extract <path d="..."> elements → sample points along each path
→ reorder paths left-to-right, top-to-bottom (simulate writing order)
→ send to frontend → animate on canvas
```

Use the `svg-path-properties` npm package (or Python equivalent `svgpathtools`) to sample evenly-spaced points along each SVG path. This gives you coordinate arrays identical in format to the handwriting model output, so the same frontend animation code handles both.

**Stroke data format (universal):**

```json
{
  "strokes": [
    {
      "points": [
        { "x": 100, "y": 200, "pressure": 0.8 },
        { "x": 102, "y": 198, "pressure": 0.75 },
        { "x": 105, "y": 195, "pressure": 0.7 }
      ],
      "color": "#FF0000",
      "width": 2
    }
  ],
  "position": { "x": 400, "y": 200 },
  "animation_speed": 1.0
}
```

### 3. Whiteboard Snapshot Pipeline

When the AI needs to "see" the board:

1. Frontend captures canvas as PNG (using `canvas.toDataURL()` or tldraw's export)
2. Sends the image to the backend via WebSocket
3. Backend includes the image in the LLM API call as a vision input alongside the conversation
4. LLM interprets what's on the board and factors it into its response

**Trigger strategies (use a combination):**

- **On pause** — if the user stops drawing for 2-3 seconds, snapshot and send
- **On voice trigger** — user says "take a look" or "what do you think"
- **Periodic** — every 5-10 seconds during active drawing (lower priority to save API calls)
- **Manual button** — "Share board with tutor" button

### 4. Voice Pipeline

```
[Mic] → WebSocket → Deepgram STT → text transcript
                                         │
                                         ▼
                                    Orchestrator
                                         │
                                         ▼
                                    LLM response
                                         │
                                    speech field
                                         │
                                         ▼
                                    ElevenLabs TTS
                                         │
                                         ▼
                              audio chunks → [Speaker]
```

Use Deepgram's streaming WebSocket API for near-real-time transcription. For TTS, ElevenLabs supports streaming audio output — start playing audio as chunks arrive rather than waiting for the full response.

### 5. Conversation State Management

The backend should maintain a session object per user:

```python
class TutorSession:
    conversation_history: list    # Full message history for LLM context
    current_subject: str          # "calculus", "algorithms", etc.
    current_topic: str            # "integration by parts"
    board_snapshots: list         # Recent whiteboard images
    tutor_mode: str               # "listening", "guiding", "demonstrating", "evaluating"
    student_progress: dict        # Track what they've gotten right/wrong
```

---

## Subject-Specific Considerations

### Calculus / Math
- Handwriting synthesis: Use the LaTeX → SVG → strokes pipeline for equations
- Vision model needs to interpret handwritten math notation (Claude and GPT-4o handle this well)
- AI should understand common mistakes (sign errors, forgetting +C, etc.)

### Algorithms / CS
- Handwriting synthesis: Standard text pipeline works perfectly (all alphanumeric)
- For code snippets: Consider rendering in clean monospace as an alternative mode
- Stretch goal: Simple diagram rendering (boxes and arrows for data structures)
- AI should be able to trace through algorithms step by step

### Physics / Engineering
- Mix of math notation and diagrams
- Free body diagrams, circuit diagrams would be amazing stretch goals
- Start with just the equation-solving interaction

---

## Hackathon MVP Priorities

### Must Have (Demo Day Core)
1. Voice conversation with AI tutor (STT + LLM + TTS pipeline working end to end)
2. Freehand whiteboard that the user can draw on
3. AI can "see" the whiteboard (vision model interprets snapshots)
4. AI can write on the whiteboard with animated handwriting (at least text → strokes)
5. Basic session flow: greeting → topic selection → problem solving → feedback

### Should Have (Makes the Demo Shine)
6. LaTeX math rendering as handwriting strokes
7. AI uses different ink colors (red for corrections, blue for hints)
8. Smooth voice with natural professor personality (good system prompt + ElevenLabs)
9. Board snapshot triggers on drawing pause (not just manual)

### Nice to Have (Stretch Goals)
10. AI draws simple diagrams (arrows, boxes, circles)
11. Eraser / board clearing by AI
12. Multiple subject support with different tutor personalities
13. Session summary / study notes export at end

---

## System Prompt (for the AI Tutor)

```
You are Professor Ada, an experienced and patient university tutor. You have a warm, 
encouraging teaching style — think of the best professor you've ever had.

PERSONALITY:
- Speak naturally and conversationally, not like a textbook
- Use phrases like "Okay, let's see what we've got here" or "Good instinct, but..."
- Be encouraging but honest — don't say something is right when it's wrong
- Use Socratic method: ask guiding questions before giving answers
- Occasionally use humor to keep things light

TEACHING APPROACH:
- Always ask the student to try first before showing them the answer
- When they make a mistake, don't just correct it — ask them to look at the specific 
  step again
- Break complex problems into smaller steps
- Use the whiteboard to illustrate key concepts
- When demonstrating, narrate what you're writing as you write it

WHITEBOARD INTERACTION:
- You can see what the student writes on the shared whiteboard
- You can write on the whiteboard too — use this for hints, corrections, and examples
- When you write on the board, describe what you're writing out loud
- Use red ink for corrections, blue for hints, green for correct work
- Circle or underline important parts

RESPONSE FORMAT:
Always respond with JSON containing:
- "speech": What you say out loud (conversational, natural)
- "board_actions": Array of whiteboard actions (write, underline, circle, clear_area)
- "tutor_state": Your current mode (listening/guiding/demonstrating/evaluating)
- "wait_for_student": Boolean — should you pause and let them work?
```

---

## Estimated Build Timeline (48-hour Hackathon)

| Phase | Hours | What to Build |
|-------|-------|---------------|
| **Setup** | 0-3 | Project scaffolding, API keys, dependencies, basic React layout |
| **Voice pipeline** | 3-8 | Deepgram STT + ElevenLabs TTS + basic LLM conversation loop |
| **Whiteboard** | 8-14 | tldraw integration, freehand drawing, canvas snapshot export |
| **Vision integration** | 14-18 | Send board snapshots to vision model, integrate into conversation context |
| **Handwriting synthesis** | 18-26 | Set up stroke generation (text + LaTeX paths), frontend animation |
| **Orchestration** | 26-32 | Wire everything together — voice + board + AI response routing |
| **Polish** | 32-40 | Professor personality tuning, UI polish, color-coded ink, error handling |
| **Demo prep** | 40-48 | Practice demo flow, fix edge cases, prepare backup scenarios |

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Handwriting synthesis model is hard to set up | Can't demo AI writing | Fallback: handwriting font + animated typing on canvas |
| Vision model misreads handwriting | AI gives wrong feedback | Use stylus for demo, practice clean handwriting, add manual "retry" option |
| Voice latency too high | Conversation feels unnatural | Use streaming for both STT and TTS, optimize LLM prompt for shorter responses |
| Too many API calls = slow | Laggy experience | Batch board snapshots, only send on meaningful changes, cache conversation context |
| WebSocket connection drops | Session breaks | Implement reconnection logic, save session state to recover |

---

## Repository Structure

```
ai-tutor/
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── TutorPanel.tsx          # AI avatar/waveform + status
│   │   │   ├── Whiteboard.tsx          # tldraw wrapper + snapshot logic
│   │   │   ├── WhiteboardOverlay.tsx   # AI handwriting animation layer
│   │   │   ├── AudioManager.tsx        # Mic input + speaker output
│   │   │   └── SessionControls.tsx     # Start/end session, subject picker
│   │   ├── hooks/
│   │   │   ├── useVoicePipeline.ts     # STT + TTS WebSocket management
│   │   │   ├── useWhiteboard.ts        # Board state, snapshots, AI strokes
│   │   │   └── useTutorSession.ts      # Session state, conversation history
│   │   ├── lib/
│   │   │   ├── strokeAnimator.ts       # Animate stroke data onto canvas
│   │   │   └── websocket.ts            # WebSocket client wrapper
│   │   └── App.tsx
│   ├── package.json
│   └── vite.config.ts
│
├── backend/
│   ├── app/
│   │   ├── main.py                     # FastAPI entry point
│   │   ├── orchestrator.py             # Routes between LLM, TTS, handwriting
│   │   ├── session.py                  # Session state management
│   │   ├── llm_client.py              # Claude/GPT-4o API calls (text + vision)
│   │   ├── tts_client.py             # ElevenLabs streaming TTS
│   │   ├── stt_client.py             # Deepgram streaming STT proxy
│   │   └── handwriting/
│   │       ├── synthesizer.py         # Text → stroke coordinates
│   │       ├── latex_to_strokes.py    # LaTeX → SVG → path sampling → strokes
│   │       └── models/               # Pretrained handwriting synthesis model
│   ├── requirements.txt
│   └── Dockerfile
│
├── .env.example                        # API keys template
├── docker-compose.yml                  # Optional: containerized setup
└── README.md
```

---

## API Keys You'll Need

| Service | What For | Free Tier? |
|---------|----------|------------|
| **Anthropic (Claude)** or **OpenAI (GPT-4o)** | Conversational AI + vision | Claude: free credits with new account. OpenAI: pay-as-you-go |
| **Deepgram** | Speech-to-text | Yes — $200 free credit on signup |
| **ElevenLabs** | Text-to-speech | Yes — limited free tier (10k chars/month). Enough for a demo. |

---

## Quick Start Commands

```bash
# Clone and setup
git clone <repo-url> && cd ai-tutor

# Backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Fill in API keys
uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```