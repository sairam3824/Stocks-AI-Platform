"""initial schema

Revision ID: 20260214_000001
Revises:
Create Date: 2026-02-14 00:00:01
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260214_000001"
down_revision = None
branch_labels = None
depends_on = None


def _column_names(bind, table: str) -> set[str]:
    rows = bind.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return {str(row[1]) for row in rows}


def _ensure_column(bind, table: str, column_name: str, ddl: str) -> None:
    if column_name in _column_names(bind, table):
        return
    bind.execute(sa.text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))


def upgrade() -> None:
    bind = op.get_bind()

    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'owner',
                plan TEXT NOT NULL DEFAULT 'free',
                max_stocks INTEGER NOT NULL DEFAULT 25,
                current_workspace_id INTEGER,
                email_verified INTEGER NOT NULL DEFAULT 0,
                email_verification_token TEXT,
                password_reset_token TEXT,
                password_reset_expires_at TEXT,
                twofa_enabled INTEGER NOT NULL DEFAULT 0,
                twofa_secret TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS workspaces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (owner_user_id) REFERENCES users(id)
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS workspace_members (
                workspace_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL DEFAULT 'member',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (workspace_id, user_id),
                FOREIGN KEY (workspace_id) REFERENCES workspaces(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS stocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                workspace_id INTEGER,
                symbol TEXT NOT NULL,
                company_name TEXT,
                market TEXT,
                stooq_symbol TEXT,
                min_return_pct REAL NOT NULL,
                max_drop_pct REAL NOT NULL,
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                workspace_id INTEGER,
                report_date TEXT NOT NULL,
                path TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (workspace_id) REFERENCES workspaces(id),
                UNIQUE (user_id, workspace_id, report_date)
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                workspace_id INTEGER,
                status TEXT NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0,
                started_at TEXT NOT NULL DEFAULT (datetime('now')),
                finished_at TEXT,
                report_date TEXT,
                message TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS job_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                workspace_id INTEGER,
                status TEXT NOT NULL DEFAULT 'QUEUED',
                attempts INTEGER NOT NULL DEFAULT 0,
                available_at TEXT NOT NULL DEFAULT (datetime('now')),
                locked_at TEXT,
                error TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (run_id) REFERENCES runs(id),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                workspace_id INTEGER,
                run_id INTEGER,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity REAL NOT NULL DEFAULT 1.0,
                reference_price REAL NOT NULL DEFAULT 0.0,
                executed_price REAL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                mode TEXT NOT NULL DEFAULT 'PAPER',
                confidence_pct REAL NOT NULL DEFAULT 0.0,
                expected_return_pct REAL NOT NULL DEFAULT 0.0,
                reasoning TEXT,
                approved_at TEXT,
                executed_at TEXT,
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (workspace_id) REFERENCES workspaces(id),
                FOREIGN KEY (run_id) REFERENCES runs(id)
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS model_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                workspace_id INTEGER,
                symbol TEXT NOT NULL,
                horizon TEXT NOT NULL,
                model_name TEXT NOT NULL,
                mape REAL NOT NULL,
                rmse REAL NOT NULL,
                selected INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS app_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_name TEXT NOT NULL,
                metric_value REAL NOT NULL,
                tags TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
    )

    _ensure_column(bind, "users", "role", "role TEXT NOT NULL DEFAULT 'owner'")
    _ensure_column(bind, "users", "plan", "plan TEXT NOT NULL DEFAULT 'free'")
    _ensure_column(bind, "users", "max_stocks", "max_stocks INTEGER NOT NULL DEFAULT 25")
    _ensure_column(bind, "users", "current_workspace_id", "current_workspace_id INTEGER")
    _ensure_column(bind, "users", "email_verified", "email_verified INTEGER NOT NULL DEFAULT 0")
    _ensure_column(bind, "users", "email_verification_token", "email_verification_token TEXT")
    _ensure_column(bind, "users", "password_reset_token", "password_reset_token TEXT")
    _ensure_column(bind, "users", "password_reset_expires_at", "password_reset_expires_at TEXT")
    _ensure_column(bind, "users", "twofa_enabled", "twofa_enabled INTEGER NOT NULL DEFAULT 0")
    _ensure_column(bind, "users", "twofa_secret", "twofa_secret TEXT")

    _ensure_column(bind, "stocks", "company_name", "company_name TEXT")
    _ensure_column(bind, "stocks", "market", "market TEXT")
    _ensure_column(bind, "stocks", "workspace_id", "workspace_id INTEGER")

    _ensure_column(bind, "runs", "progress", "progress INTEGER NOT NULL DEFAULT 0")
    _ensure_column(bind, "runs", "workspace_id", "workspace_id INTEGER")
    _ensure_column(bind, "runs", "created_at", "created_at TEXT")

    _ensure_column(bind, "reports", "workspace_id", "workspace_id INTEGER")

    op.execute(
        sa.text(
            """
            INSERT INTO workspaces (owner_user_id, name)
            SELECT u.id, 'Personal'
            FROM users u
            WHERE NOT EXISTS (
                SELECT 1 FROM workspaces w WHERE w.owner_user_id = u.id
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT OR IGNORE INTO workspace_members (workspace_id, user_id, role)
            SELECT w.id, w.owner_user_id, 'owner'
            FROM workspaces w
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE users
            SET current_workspace_id = (
                SELECT w.id
                FROM workspaces w
                WHERE w.owner_user_id = users.id
                ORDER BY w.id
                LIMIT 1
            )
            WHERE IFNULL(current_workspace_id, 0) = 0
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE stocks
            SET workspace_id = (
                SELECT u.current_workspace_id
                FROM users u
                WHERE u.id = stocks.user_id
            )
            WHERE IFNULL(workspace_id, 0) = 0
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE reports
            SET workspace_id = (
                SELECT u.current_workspace_id
                FROM users u
                WHERE u.id = reports.user_id
            )
            WHERE IFNULL(workspace_id, 0) = 0
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE runs
            SET workspace_id = (
                SELECT u.current_workspace_id
                FROM users u
                WHERE u.id = runs.user_id
            )
            WHERE IFNULL(workspace_id, 0) = 0
            """
        )
    )
    op.execute(sa.text("UPDATE runs SET created_at = datetime('now') WHERE created_at IS NULL"))

    op.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_stocks_user_workspace_symbol
              ON stocks(user_id, workspace_id, symbol)
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_reports_user_workspace_date
              ON reports(user_id, workspace_id, report_date DESC)
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_runs_user_workspace_started
              ON runs(user_id, workspace_id, started_at DESC)
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_job_queue_status_available
              ON job_queue(status, available_at, id)
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_trades_user_workspace_status
              ON trades(user_id, workspace_id, status, created_at DESC)
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_model_metrics_user_workspace_symbol
              ON model_metrics(user_id, workspace_id, symbol, created_at DESC)
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_users_email_verification_token
              ON users(email_verification_token)
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_users_password_reset_token
              ON users(password_reset_token)
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS app_metrics"))
    op.execute(sa.text("DROP TABLE IF EXISTS model_metrics"))
    op.execute(sa.text("DROP TABLE IF EXISTS trades"))
    op.execute(sa.text("DROP TABLE IF EXISTS job_queue"))
    op.execute(sa.text("DROP TABLE IF EXISTS runs"))
    op.execute(sa.text("DROP TABLE IF EXISTS reports"))
    op.execute(sa.text("DROP TABLE IF EXISTS stocks"))
    op.execute(sa.text("DROP TABLE IF EXISTS workspace_members"))
    op.execute(sa.text("DROP TABLE IF EXISTS workspaces"))
    op.execute(sa.text("DROP TABLE IF EXISTS users"))
