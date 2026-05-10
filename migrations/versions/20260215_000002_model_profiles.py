"""model profiles and quality extensions

Revision ID: 20260215_000002
Revises: 20260214_000001
Create Date: 2026-02-15 00:00:02
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260215_000002"
down_revision = "20260214_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS model_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                workspace_id INTEGER,
                symbol TEXT NOT NULL,
                horizon TEXT NOT NULL,
                preferred_model TEXT NOT NULL,
                last_mape REAL NOT NULL DEFAULT 0.0,
                last_rmse REAL NOT NULL DEFAULT 0.0,
                sample_count INTEGER NOT NULL DEFAULT 0,
                last_trained_at TEXT NOT NULL DEFAULT (datetime('now')),
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (workspace_id) REFERENCES workspaces(id),
                UNIQUE (user_id, workspace_id, symbol, horizon)
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_model_profiles_user_workspace_symbol
              ON model_profiles(user_id, workspace_id, symbol, horizon, last_trained_at DESC)
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS model_profiles"))
