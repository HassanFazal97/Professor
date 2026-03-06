import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Notebook, Page, TutorSessionRecord, User

router = APIRouter()

PaperStyle = Literal["blank", "lined", "graph"]


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class NotebookOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    subject: str | None
    color: str
    emoji: str
    created_at: datetime
    updated_at: datetime


class NotebookCreateBody(BaseModel):
    title: str
    subject: str | None = None
    color: str = "#6366f1"
    emoji: str = "📒"


class NotebookUpdateBody(BaseModel):
    title: str | None = None
    subject: str | None = None
    color: str | None = None
    emoji: str | None = None


class PageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    notebook_id: uuid.UUID
    title: str
    page_number: int
    paper_style: str
    created_at: datetime
    updated_at: datetime


class PageCreateBody(BaseModel):
    title: str
    paper_style: PaperStyle = "blank"


class PageUpdateBody(BaseModel):
    title: str | None = None
    paper_style: PaperStyle | None = None


class SessionStateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    page_id: uuid.UUID
    current_subject: str | None
    tutor_mode: str | None
    board_next_y: int
    board_viewport_y: int
    student_content_bottom_y: int
    board_width: int
    board_height: int
    conversation_history: list
    tldraw_snapshot: dict | None
    overlay_strokes: list


class SessionSaveBody(BaseModel):
    tldraw_snapshot: dict | None = None
    overlay_strokes: list = []


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_notebook_owned(
    notebook_id: str, user: User, db: AsyncSession
) -> Notebook:
    result = await db.execute(
        select(Notebook).where(
            Notebook.id == uuid.UUID(notebook_id),
            Notebook.user_id == user.id,
        )
    )
    nb = result.scalar_one_or_none()
    if not nb:
        raise HTTPException(status_code=404, detail="Notebook not found")
    return nb


async def _get_page_owned(page_id: str, user: User, db: AsyncSession) -> Page:
    result = await db.execute(
        select(Page)
        .join(Notebook)
        .where(Page.id == uuid.UUID(page_id), Notebook.user_id == user.id)
    )
    page = result.scalar_one_or_none()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return page


# ── Notebooks ─────────────────────────────────────────────────────────────────

@router.get("/notebooks", response_model=list[NotebookOut])
async def list_notebooks(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Notebook)
        .where(Notebook.user_id == user.id)
        .order_by(Notebook.created_at.desc())
    )
    return result.scalars().all()


@router.post("/notebooks", response_model=NotebookOut, status_code=201)
async def create_notebook(
    body: NotebookCreateBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    nb = Notebook(
        user_id=user.id,
        title=body.title,
        subject=body.subject,
        color=body.color,
        emoji=body.emoji,
    )
    db.add(nb)
    await db.commit()
    await db.refresh(nb)
    return nb


@router.patch("/notebooks/{notebook_id}", response_model=NotebookOut)
async def update_notebook(
    notebook_id: str,
    body: NotebookUpdateBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    nb = await _get_notebook_owned(notebook_id, user, db)
    if body.title is not None:
        nb.title = body.title
    if body.subject is not None:
        nb.subject = body.subject
    if body.color is not None:
        nb.color = body.color
    if body.emoji is not None:
        nb.emoji = body.emoji
    await db.commit()
    await db.refresh(nb)
    return nb


@router.delete("/notebooks/{notebook_id}", status_code=204)
async def delete_notebook(
    notebook_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    nb = await _get_notebook_owned(notebook_id, user, db)
    await db.delete(nb)
    await db.commit()


# ── Pages ─────────────────────────────────────────────────────────────────────

@router.get("/notebooks/{notebook_id}/pages", response_model=list[PageOut])
async def list_pages(
    notebook_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_notebook_owned(notebook_id, user, db)
    result = await db.execute(
        select(Page)
        .where(Page.notebook_id == uuid.UUID(notebook_id))
        .order_by(Page.page_number)
    )
    return result.scalars().all()


@router.post("/notebooks/{notebook_id}/pages", response_model=PageOut, status_code=201)
async def create_page(
    notebook_id: str,
    body: PageCreateBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    nb = await _get_notebook_owned(notebook_id, user, db)
    # Auto-increment page number
    result = await db.execute(
        select(func.max(Page.page_number)).where(Page.notebook_id == nb.id)
    )
    max_num = result.scalar() or 0
    page = Page(
        notebook_id=nb.id,
        title=body.title,
        page_number=max_num + 1,
        paper_style=body.paper_style,
    )
    db.add(page)
    await db.commit()
    await db.refresh(page)
    return page


@router.get("/pages/{page_id}", response_model=PageOut)
async def get_page(
    page_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _get_page_owned(page_id, user, db)


@router.patch("/pages/{page_id}", response_model=PageOut)
async def update_page(
    page_id: str,
    body: PageUpdateBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    page = await _get_page_owned(page_id, user, db)
    if body.title is not None:
        page.title = body.title
    if body.paper_style is not None:
        page.paper_style = body.paper_style
    await db.commit()
    await db.refresh(page)
    return page


@router.delete("/pages/{page_id}", status_code=204)
async def delete_page(
    page_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    page = await _get_page_owned(page_id, user, db)
    await db.delete(page)
    await db.commit()


# ── Session save/restore ──────────────────────────────────────────────────────

@router.get("/pages/{page_id}/session", response_model=SessionStateOut | None)
async def get_page_session(
    page_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    page = await _get_page_owned(page_id, user, db)
    result = await db.execute(
        select(TutorSessionRecord).where(TutorSessionRecord.page_id == page.id)
    )
    record = result.scalar_one_or_none()
    if not record:
        return None
    return record


@router.put("/pages/{page_id}/session", response_model=SessionStateOut)
async def save_page_session(
    page_id: str,
    body: SessionSaveBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Frontend calls this on unload to save tldraw snapshot + overlay strokes."""
    page = await _get_page_owned(page_id, user, db)
    result = await db.execute(
        select(TutorSessionRecord).where(TutorSessionRecord.page_id == page.id)
    )
    record = result.scalar_one_or_none()

    if record:
        record.tldraw_snapshot = body.tldraw_snapshot
        record.overlay_strokes = body.overlay_strokes
    else:
        record = TutorSessionRecord(
            page_id=page.id,
            user_id=user.id,
            tldraw_snapshot=body.tldraw_snapshot,
            overlay_strokes=body.overlay_strokes or [],
        )
        db.add(record)

    await db.commit()
    await db.refresh(record)
    return record
