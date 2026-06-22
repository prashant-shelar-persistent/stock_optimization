"""Add frontier_report JSON column to optimization_runs.

Revision ID: 002
Revises: 001
Create Date: 2026-06-15 12:00:00.000000 UTC

This additive migration introduces the ``frontier_report`` JSON column
on ``optimization_runs``. The column stores the full bundled output of
the efficient-frontier sweep (points, dominant set, knee point,
reference portfolios, and LLM commentary) for runs where the user
enabled ``frontier.enabled = true`` in the optimisation request.

Backward compatibility:
    - The column is nullable; existing rows are unaffected.
    - Legacy runs continue to deserialise correctly because the
      Pydantic ``OptimizationRunDetail.frontier_report`` field defaults
      to ``None``.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable ``frontier_report`` JSON column."""
    op.add_column(
        "optimization_runs",
        sa.Column(
            "frontier_report",
            sa.JSON(),
            nullable=True,
            comment=(
                "Serialised FrontierReport (efficient-frontier bundle) — "
                "null when the request did not enable the frontier sweep"
            ),
        ),
    )


def downgrade() -> None:
    """Drop the ``frontier_report`` column."""
    op.drop_column("optimization_runs", "frontier_report")
