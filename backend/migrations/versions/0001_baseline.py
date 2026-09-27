"""Baseline: the articles table as it existed before migrations were introduced.

Databases created earlier by `Base.metadata.create_all` already have this schema;
init_db stamps them at this revision instead of re-creating the table.

Revision ID: 0001
Revises:
Create Date: 2026-09-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "articles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("url", sa.String(length=2000), nullable=False),
        sa.Column("source", sa.String(length=200), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_content", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("deep_explanation", sa.Text(), nullable=True),
        sa.Column("why_it_matters", sa.Text(), nullable=True),
        sa.Column("background_info", sa.Text(), nullable=True),
        sa.Column("importance_score", sa.Float(), nullable=True),
        sa.Column("is_trending", sa.Boolean(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url"),
    )
    op.create_index("ix_articles_id", "articles", ["id"])
    op.create_index("ix_articles_category", "articles", ["category"])
    op.create_index("ix_articles_fetched_at", "articles", ["fetched_at"])


def downgrade() -> None:
    op.drop_index("ix_articles_fetched_at", table_name="articles")
    op.drop_index("ix_articles_category", table_name="articles")
    op.drop_index("ix_articles_id", table_name="articles")
    op.drop_table("articles")
