import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    google_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    notebooks: Mapped[list["Notebook"]] = relationship(
        "Notebook", back_populates="user", cascade="all, delete-orphan"
    )


class Notebook(Base):
    __tablename__ = "notebooks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    color: Mapped[str] = mapped_column(String(20), default="#6366f1")
    emoji: Mapped[str] = mapped_column(String(10), default="📒")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship("User", back_populates="notebooks")
    pages: Mapped[list["Page"]] = relationship(
        "Page", back_populates="notebook", cascade="all, delete-orphan"
    )


class Page(Base):
    __tablename__ = "pages"
    __table_args__ = (UniqueConstraint("notebook_id", "page_number"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    notebook_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notebooks.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    paper_style: Mapped[str] = mapped_column(
        Enum("blank", "lined", "graph", name="paper_style_enum"), default="blank"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    notebook: Mapped[Notebook] = relationship("Notebook", back_populates="pages")
    tutor_session: Mapped["TutorSessionRecord | None"] = relationship(
        "TutorSessionRecord", back_populates="page", uselist=False,
        cascade="all, delete-orphan"
    )


class TutorSessionRecord(Base):
    __tablename__ = "tutor_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pages.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    current_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tutor_mode: Mapped[str | None] = mapped_column(String(50), nullable=True)
    board_next_y: Mapped[int] = mapped_column(Integer, default=0)
    board_viewport_y: Mapped[int] = mapped_column(Integer, default=0)
    student_content_bottom_y: Mapped[int] = mapped_column(Integer, default=0)
    board_width: Mapped[int] = mapped_column(Integer, default=1200)
    board_height: Mapped[int] = mapped_column(Integer, default=700)
    conversation_history: Mapped[list] = mapped_column(JSON, default=list)
    # Saved by frontend on unload:
    tldraw_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    overlay_strokes: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    page: Mapped[Page] = relationship("Page", back_populates="tutor_session")
    user: Mapped[User] = relationship("User")
