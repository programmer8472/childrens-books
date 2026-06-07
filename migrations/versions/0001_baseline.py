"""baseline (empty) — schema arrives in Unit 1

Revision ID: 0001_baseline
Revises:
Create Date: 2026-06-07

"""
from collections.abc import Sequence

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Intentionally empty. Unit 1 adds the real tables.
    pass


def downgrade() -> None:
    pass
