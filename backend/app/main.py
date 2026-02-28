import os
import uuid
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.orchestrator import Orchestrator
from app.session import TutorSession

load_dotenv()

sessions: dict[str, TutorSession] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("AI Tutor backend starting up...")
    yield
    print("AI Tutor backend shutting down...")


app = FastAPI(title="AI Tutor API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_URL", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "0.1.0"}


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()

    if session_id not in sessions:
        sessions[session_id] = TutorSession(session_id=session_id)

    session = sessions[session_id]
    orchestrator = Orchestrator(session=session, websocket=websocket)

    try:
        await orchestrator.on_connect()
        while True:
            data = await websocket.receive_json()
            await orchestrator.handle_message(data)
    except WebSocketDisconnect:
        print(f"Session {session_id} disconnected")
        sessions.pop(session_id, None)
    except Exception as e:
        print(f"Error in session {session_id}: {e}")
        await websocket.close(code=1011, reason=str(e))
        sessions.pop(session_id, None)


@app.get("/session/new")
async def new_session():
    session_id = str(uuid.uuid4())
    return {"session_id": session_id}
