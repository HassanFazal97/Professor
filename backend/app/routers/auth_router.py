import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import (
    create_access_token,
    hash_password,
    verify_google_token,
    verify_password,
)
from app.database import get_db
from app.dependencies import get_current_user
from app.models import User

router = APIRouter()


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str | None
    avatar_url: str | None
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class RegisterBody(BaseModel):
    email: str
    password: str
    display_name: str | None = None


class LoginBody(BaseModel):
    email: str
    password: str


class GoogleBody(BaseModel):
    id_token: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _token_response(user: User) -> TokenResponse:
    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterBody, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        display_name=body.display_name or body.email.split("@")[0],
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return _token_response(user)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginBody, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not user.hashed_password or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return _token_response(user)


@router.post("/google", response_model=TokenResponse)
async def google_auth(body: GoogleBody, db: AsyncSession = Depends(get_db)):
    try:
        info = await verify_google_token(body.id_token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    # Try to find by google_id first, then by email
    result = await db.execute(select(User).where(User.google_id == info["sub"]))
    user = result.scalar_one_or_none()

    if not user:
        result = await db.execute(select(User).where(User.email == info["email"]))
        user = result.scalar_one_or_none()

    if user:
        # Link google_id if not already set
        if not user.google_id:
            user.google_id = info["sub"]
        if info.get("picture") and not user.avatar_url:
            user.avatar_url = info["picture"]
        await db.commit()
        await db.refresh(user)
    else:
        user = User(
            email=info["email"],
            google_id=info["sub"],
            display_name=info.get("name") or info["email"].split("@")[0],
            avatar_url=info.get("picture"),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    return _token_response(user)


@router.get("/me", response_model=UserOut)
async def me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return UserOut.model_validate(current_user)
