"""Story grouping: articles covering the same event share a cluster_id.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("articles") as batch:
        batch.add_column(sa.Column("cluster_id", sa.Integer(), nullable=True))
        batch.create_index("ix_articles_cluster_id", ["cluster_id"])


def downgrade() -> None:
    with op.batch_alter_table("articles") as batch:
        batch.drop_index("ix_articles_cluster_id")
        batch.drop_column("cluster_id")
