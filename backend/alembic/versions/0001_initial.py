"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-03-05

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=True),
        sa.Column("google_id", sa.String(255), nullable=True),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("avatar_url", sa.String(512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("google_id"),
    )

    op.create_table(
        "notebooks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("subject", sa.String(255), nullable=True),
        sa.Column("color", sa.String(20), nullable=False, server_default="#6366f1"),
        sa.Column("emoji", sa.String(10), nullable=False, server_default="📒"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    paper_style_enum = postgresql.ENUM(
        "blank", "lined", "graph", name="paper_style_enum", create_type=True
    )
    paper_style_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "pages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notebook_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column(
            "paper_style",
            sa.Enum("blank", "lined", "graph", name="paper_style_enum"),
            nullable=False,
            server_default="blank",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["notebook_id"], ["notebooks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("notebook_id", "page_number"),
    )

    op.create_table(
        "tutor_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("page_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("current_subject", sa.String(255), nullable=True),
        sa.Column("tutor_mode", sa.String(50), nullable=True),
        sa.Column("board_next_y", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("board_viewport_y", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "student_content_bottom_y", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("board_width", sa.Integer(), nullable=False, server_default="1200"),
        sa.Column("board_height", sa.Integer(), nullable=False, server_default="700"),
        sa.Column("conversation_history", postgresql.JSON(), nullable=False, server_default="[]"),
        sa.Column("tldraw_snapshot", postgresql.JSON(), nullable=True),
        sa.Column("overlay_strokes", postgresql.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["page_id"], ["pages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("page_id"),
    )


def downgrade() -> None:
    op.drop_table("tutor_sessions")
    op.drop_table("pages")
    op.execute("DROP TYPE IF EXISTS paper_style_enum")
    op.drop_table("notebooks")
    op.drop_table("users")
