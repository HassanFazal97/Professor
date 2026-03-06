import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.database import AsyncSessionLocal, dispose_db, init_db
from app.models import Notebook, Page, TutorSessionRecord
from app.orchestrator import Orchestrator
from app.routers import auth_router, notebooks_router
from app.session import TutorSession

# Use __file__ so this always resolves correctly regardless of CWD.
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_env_path, override=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("AI Tutor backend starting up...")
    await init_db()
    yield
    print("AI Tutor backend shutting down...")
    await dispose_db()


app = FastAPI(title="AI Tutor API", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_URL", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router, prefix="/auth", tags=["auth"])
app.include_router(notebooks_router.router, tags=["notebooks"])


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "0.2.0"}


@app.websocket("/ws/{page_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    page_id: str,
    token: str = Query(None),
):
    # 1. Verify token → user
    from app.auth import decode_access_token
    from app.models import User

    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return

    async with AsyncSessionLocal() as db:
        try:
            user_id = decode_access_token(token)
        except ValueError:
            await websocket.close(code=4001, reason="Invalid token")
            return

        result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
        user = result.scalar_one_or_none()
        if not user:
            await websocket.close(code=4001, reason="User not found")
            return

        # 2. Verify page belongs to this user
        try:
            page_uuid = uuid.UUID(page_id)
        except ValueError:
            await websocket.close(code=4002, reason="Invalid page_id")
            return

        result = await db.execute(
            select(Page).join(Notebook).where(
                Page.id == page_uuid,
                Notebook.user_id == user.id,
            )
        )
        page = result.scalar_one_or_none()
        if not page:
            await websocket.close(code=4003, reason="Page not found")
            return

        # 3. Accept WebSocket
        await websocket.accept()

        # 4. Load or create TutorSession from DB
        result = await db.execute(
            select(TutorSessionRecord).where(TutorSessionRecord.page_id == page_uuid)
        )
        record = result.scalar_one_or_none()

        if record:
            session = TutorSession.from_db_record(record, page_id)
        else:
            session = TutorSession(session_id=page_id)

        # 5. Create Orchestrator with DB session
        orchestrator = Orchestrator(session=session, websocket=websocket, db=db, user_id=user_id)

        try:
            await orchestrator.on_connect()
            while True:
                data = await websocket.receive_json()
                await orchestrator.handle_message(data)
        except WebSocketDisconnect:
            print(f"Page {page_id} disconnected")
            await orchestrator._save_session_to_db()
            orchestrator.cleanup()
        except Exception as e:
            print(f"Error in page {page_id}: {e}")
            try:
                await orchestrator._save_session_to_db()
            except Exception:
                pass
            orchestrator.cleanup()
            await websocket.close(code=1011, reason=str(e)[:100])


# Legacy unauthenticated endpoint kept for local dev without DB
@app.websocket("/ws-dev/{session_id}")
async def websocket_dev_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    session = TutorSession(session_id=session_id)
    orchestrator = Orchestrator(session=session, websocket=websocket)
    try:
        await orchestrator.on_connect()
        while True:
            data = await websocket.receive_json()
            await orchestrator.handle_message(data)
    except WebSocketDisconnect:
        print(f"Dev session {session_id} disconnected")
        orchestrator.cleanup()
    except Exception as e:
        print(f"Error in dev session {session_id}: {e}")
        orchestrator.cleanup()
        await websocket.close(code=1011, reason=str(e)[:100])


@app.get("/session/new")
async def new_session():
    session_id = str(uuid.uuid4())
    return {"session_id": session_id}
