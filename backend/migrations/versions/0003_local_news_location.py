"""Local news: where a story was found (country / state / district).

Local stories are stored with category 'local' and the location they were fetched for,
so the Local page can serve them without refetching and they open in the article page.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("articles") as batch:
        batch.add_column(sa.Column("loc_country", sa.String(length=2), nullable=True))
        batch.add_column(sa.Column("loc_state", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("loc_district", sa.String(length=100), nullable=True))
        batch.create_index("ix_articles_location", ["loc_country", "loc_state", "loc_district"])


def downgrade() -> None:
    with op.batch_alter_table("articles") as batch:
        batch.drop_index("ix_articles_location")
        batch.drop_column("loc_district")
        batch.drop_column("loc_state")
        batch.drop_column("loc_country")
