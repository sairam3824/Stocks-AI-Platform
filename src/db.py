from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class User:
    id: int
    email: str
    password_hash: str
    role: str = "owner"
    plan: str = "free"
    max_stocks: int = 25
    current_workspace_id: int = 0
    email_verified: int = 0
    email_verification_token: str = ""
    password_reset_token: str = ""
    password_reset_expires_at: str = ""
    twofa_enabled: int = 0
    twofa_secret: str = ""


@dataclass
class Workspace:
    id: int
    owner_user_id: int
    name: str


@dataclass
class WorkspaceMember:
    workspace_id: int
    user_id: int
    role: str


@dataclass
class Stock:
    id: int
    user_id: int
    workspace_id: int
    symbol: str
    company_name: str
    market: str
    stooq_symbol: Optional[str]
    min_return_pct: float
    max_drop_pct: float
    notes: str


@dataclass
class Report:
    id: int
    user_id: int
    workspace_id: int
    report_date: str
    path: str


@dataclass
class Run:
    id: int
    user_id: int
    workspace_id: int
    status: str
    started_at: str
    finished_at: str
    report_date: str
    message: str
    progress: int


@dataclass
class Job:
    id: int
    run_id: int
    user_id: int
    workspace_id: int
    status: str
    attempts: int
    available_at: str
    locked_at: str
    error: str


@dataclass
class Trade:
    id: int
    user_id: int
    workspace_id: int
    run_id: int
    symbol: str
    side: str
    quantity: float
    reference_price: float
    executed_price: float
    status: str
    mode: str
    confidence_pct: float
    expected_return_pct: float
    reasoning: str
    approved_at: str
    executed_at: str
    notes: str


@dataclass
class ModelMetric:
    id: int
    user_id: int
    workspace_id: int
    symbol: str
    horizon: str
    model_name: str
    mape: float
    rmse: float
    selected: int
    created_at: str


@dataclass
class ModelProfile:
    id: int
    user_id: int
    workspace_id: int
    symbol: str
    horizon: str
    preferred_model: str
    last_mape: float
    last_rmse: float
    sample_count: int
    last_trained_at: str


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


def _column_names(conn: sqlite3.Connection, table: str) -> List[str]:
    return [row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def _ensure_default_workspace(conn: sqlite3.Connection, user_id: int) -> int:
    row = conn.execute(
        "SELECT id FROM workspaces WHERE owner_user_id = ? ORDER BY id LIMIT 1",
        (user_id,),
    ).fetchone()
    if row:
        workspace_id = int(row["id"])
    else:
        result = conn.execute(
            "INSERT INTO workspaces (owner_user_id, name) VALUES (?, ?)",
            (user_id, "Personal"),
        )
        workspace_id = int(result.lastrowid)
    conn.execute(
        """
        INSERT OR IGNORE INTO workspace_members (workspace_id, user_id, role)
        VALUES (?, ?, ?)
        """,
        (workspace_id, user_id, "owner"),
    )
    conn.execute(
        "UPDATE users SET current_workspace_id = COALESCE(current_workspace_id, ?) WHERE id = ?",
        (workspace_id, user_id),
    )
    conn.execute(
        "UPDATE users SET current_workspace_id = ? WHERE id = ? AND IFNULL(current_workspace_id, 0) = 0",
        (workspace_id, user_id),
    )
    return workspace_id


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        conn.executescript(
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
            );

            CREATE TABLE IF NOT EXISTS workspaces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (owner_user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS workspace_members (
                workspace_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL DEFAULT 'member',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (workspace_id, user_id),
                FOREIGN KEY (workspace_id) REFERENCES workspaces(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

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
            );

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
            );

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
            );

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
            );

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
            );

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
            );

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
            );

            CREATE TABLE IF NOT EXISTS app_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_name TEXT NOT NULL,
                metric_value REAL NOT NULL,
                tags TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )

        user_columns = _column_names(conn, "users")
        if "role" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'owner'")
        if "plan" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN plan TEXT NOT NULL DEFAULT 'free'")
        if "max_stocks" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN max_stocks INTEGER NOT NULL DEFAULT 25")
        if "current_workspace_id" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN current_workspace_id INTEGER")
        if "email_verified" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0")
        if "email_verification_token" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN email_verification_token TEXT")
        if "password_reset_token" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN password_reset_token TEXT")
        if "password_reset_expires_at" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN password_reset_expires_at TEXT")
        if "twofa_enabled" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN twofa_enabled INTEGER NOT NULL DEFAULT 0")
        if "twofa_secret" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN twofa_secret TEXT")

        stock_columns = _column_names(conn, "stocks")
        if "company_name" not in stock_columns:
            conn.execute("ALTER TABLE stocks ADD COLUMN company_name TEXT")
        if "market" not in stock_columns:
            conn.execute("ALTER TABLE stocks ADD COLUMN market TEXT")
        if "workspace_id" not in stock_columns:
            conn.execute("ALTER TABLE stocks ADD COLUMN workspace_id INTEGER")

        run_columns = _column_names(conn, "runs")
        if "progress" not in run_columns:
            conn.execute("ALTER TABLE runs ADD COLUMN progress INTEGER DEFAULT 0")
        if "workspace_id" not in run_columns:
            conn.execute("ALTER TABLE runs ADD COLUMN workspace_id INTEGER")
        if "created_at" not in run_columns:
            conn.execute("ALTER TABLE runs ADD COLUMN created_at TEXT")
            conn.execute("UPDATE runs SET created_at = datetime('now') WHERE created_at IS NULL")

        report_columns = _column_names(conn, "reports")
        if "workspace_id" not in report_columns:
            conn.execute("ALTER TABLE reports ADD COLUMN workspace_id INTEGER")

        users = conn.execute("SELECT id FROM users").fetchall()
        for row in users:
            user_id = int(row["id"])
            workspace_id = _ensure_default_workspace(conn, user_id)
            conn.execute(
                "UPDATE stocks SET workspace_id = ? WHERE user_id = ? AND IFNULL(workspace_id, 0) = 0",
                (workspace_id, user_id),
            )
            conn.execute(
                "UPDATE reports SET workspace_id = ? WHERE user_id = ? AND IFNULL(workspace_id, 0) = 0",
                (workspace_id, user_id),
            )
            conn.execute(
                "UPDATE runs SET workspace_id = ? WHERE user_id = ? AND IFNULL(workspace_id, 0) = 0",
                (workspace_id, user_id),
            )

        conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_stocks_user_workspace_symbol
              ON stocks(user_id, workspace_id, symbol);
            CREATE INDEX IF NOT EXISTS idx_reports_user_workspace_date
              ON reports(user_id, workspace_id, report_date DESC);
            CREATE INDEX IF NOT EXISTS idx_runs_user_workspace_started
              ON runs(user_id, workspace_id, started_at DESC);
            CREATE INDEX IF NOT EXISTS idx_job_queue_status_available
              ON job_queue(status, available_at, id);
            CREATE INDEX IF NOT EXISTS idx_trades_user_workspace_status
              ON trades(user_id, workspace_id, status, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_model_metrics_user_workspace_symbol
              ON model_metrics(user_id, workspace_id, symbol, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_model_profiles_user_workspace_symbol
              ON model_profiles(user_id, workspace_id, symbol, horizon, last_trained_at DESC);
            CREATE INDEX IF NOT EXISTS idx_users_email_verification_token
              ON users(email_verification_token);
            CREATE INDEX IF NOT EXISTS idx_users_password_reset_token
              ON users(password_reset_token);
            """
        )


def _build_user(row: sqlite3.Row) -> User:
    return User(
        id=int(row["id"]),
        email=str(row["email"]),
        password_hash=str(row["password_hash"]),
        role=str(row["role"] or "owner"),
        plan=str(row["plan"] or "free"),
        max_stocks=int(row["max_stocks"] or 25),
        current_workspace_id=int(row["current_workspace_id"] or 0),
        email_verified=int(row["email_verified"] or 0),
        email_verification_token=str(row["email_verification_token"] or ""),
        password_reset_token=str(row["password_reset_token"] or ""),
        password_reset_expires_at=str(row["password_reset_expires_at"] or ""),
        twofa_enabled=int(row["twofa_enabled"] or 0),
        twofa_secret=str(row["twofa_secret"] or ""),
    )


def get_user_workspace_id(db_path: Path, user_id: int) -> int:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT current_workspace_id FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if row and int(row["current_workspace_id"] or 0) > 0:
            return int(row["current_workspace_id"])
        return _ensure_default_workspace(conn, user_id)


def create_user(
    db_path: Path,
    email: str,
    password_hash: str,
    email_verified: int = 0,
    email_verification_token: str = "",
) -> User:
    with connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO users (
                email, password_hash, role, plan, max_stocks, email_verified, email_verification_token
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (email.lower(), password_hash, "owner", "free", 25, int(email_verified), email_verification_token or None),
        )
        user_id = int(cursor.lastrowid)
        workspace_id = _ensure_default_workspace(conn, user_id)
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        user = _build_user(row)
        user.current_workspace_id = workspace_id
        return user


def get_user_by_email(db_path: Path, email: str) -> Optional[User]:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email.lower(),)).fetchone()
    if row is None:
        return None
    return _build_user(row)


def get_user_by_id(db_path: Path, user_id: int) -> Optional[User]:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        return None
    return _build_user(row)


def set_email_verification_token(db_path: Path, user_id: int, token: str) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE users SET email_verification_token = ?, email_verified = 0 WHERE id = ?",
            (token, user_id),
        )


def get_user_by_email_verification_token(db_path: Path, token: str) -> Optional[User]:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE email_verification_token = ?",
            (token,),
        ).fetchone()
    if row is None:
        return None
    return _build_user(row)


def verify_user_email(db_path: Path, user_id: int) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE users SET email_verified = 1, email_verification_token = NULL WHERE id = ?",
            (user_id,),
        )


def set_password_reset_token(
    db_path: Path,
    user_id: int,
    token: str,
    expires_at: str,
) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE users
            SET password_reset_token = ?, password_reset_expires_at = ?
            WHERE id = ?
            """,
            (token, expires_at, user_id),
        )


def get_user_by_reset_token(db_path: Path, token: str) -> Optional[User]:
    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT *
            FROM users
            WHERE password_reset_token = ?
              AND password_reset_expires_at IS NOT NULL
              AND password_reset_expires_at > datetime('now')
            """,
            (token,),
        ).fetchone()
    if row is None:
        return None
    return _build_user(row)


def update_user_password(db_path: Path, user_id: int, password_hash: str) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE users
            SET password_hash = ?,
                password_reset_token = NULL,
                password_reset_expires_at = NULL
            WHERE id = ?
            """,
            (password_hash, user_id),
        )


def set_twofa_secret(db_path: Path, user_id: int, secret: str, enabled: int) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE users
            SET twofa_secret = ?, twofa_enabled = ?
            WHERE id = ?
            """,
            (secret, int(enabled), user_id),
        )


def disable_twofa(db_path: Path, user_id: int) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE users SET twofa_enabled = 0, twofa_secret = NULL WHERE id = ?",
            (user_id,),
        )


def get_workspace_member_role(db_path: Path, user_id: int, workspace_id: int) -> str:
    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT role
            FROM workspace_members
            WHERE workspace_id = ? AND user_id = ?
            """,
            (workspace_id, user_id),
        ).fetchone()
    if row is None:
        return "none"
    return str(row["role"] or "member")


def set_user_workspace(db_path: Path, user_id: int, workspace_id: int) -> None:
    with connect(db_path) as conn:
        member = conn.execute(
            "SELECT 1 FROM workspace_members WHERE workspace_id = ? AND user_id = ?",
            (workspace_id, user_id),
        ).fetchone()
        if member is None:
            raise ValueError("User is not part of that workspace")
        conn.execute(
            "UPDATE users SET current_workspace_id = ? WHERE id = ?",
            (workspace_id, user_id),
        )


def list_workspaces(db_path: Path, user_id: int) -> List[Workspace]:
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT w.*
            FROM workspaces w
            JOIN workspace_members m ON m.workspace_id = w.id
            WHERE m.user_id = ?
            ORDER BY w.id
            """,
            (user_id,),
        ).fetchall()
    return [
        Workspace(id=int(row["id"]), owner_user_id=int(row["owner_user_id"]), name=str(row["name"]))
        for row in rows
    ]


def list_stocks(db_path: Path, user_id: int, workspace_id: int | None = None) -> List[Stock]:
    workspace_id = workspace_id or get_user_workspace_id(db_path, user_id)
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM stocks
            WHERE user_id = ? AND workspace_id = ?
            ORDER BY symbol
            """,
            (user_id, workspace_id),
        ).fetchall()
    return [
        Stock(
            id=int(row["id"]),
            user_id=int(row["user_id"]),
            workspace_id=int(row["workspace_id"] or 0),
            symbol=str(row["symbol"]),
            company_name=str(row["company_name"] or ""),
            market=str(row["market"] or ""),
            stooq_symbol=row["stooq_symbol"],
            min_return_pct=float(row["min_return_pct"]),
            max_drop_pct=float(row["max_drop_pct"]),
            notes=str(row["notes"] or ""),
        )
        for row in rows
    ]


def list_all_stocks(db_path: Path) -> List[Stock]:
    with connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM stocks ORDER BY symbol").fetchall()
    return [
        Stock(
            id=int(row["id"]),
            user_id=int(row["user_id"]),
            workspace_id=int(row["workspace_id"] or 0),
            symbol=str(row["symbol"]),
            company_name=str(row["company_name"] or ""),
            market=str(row["market"] or ""),
            stooq_symbol=row["stooq_symbol"],
            min_return_pct=float(row["min_return_pct"]),
            max_drop_pct=float(row["max_drop_pct"]),
            notes=str(row["notes"] or ""),
        )
        for row in rows
    ]


def count_stocks(db_path: Path, user_id: int, workspace_id: int | None = None) -> int:
    workspace_id = workspace_id or get_user_workspace_id(db_path, user_id)
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM stocks WHERE user_id = ? AND workspace_id = ?",
            (user_id, workspace_id),
        ).fetchone()
    return int(row["c"] if row else 0)


def add_stock(
    db_path: Path,
    user_id: int,
    symbol: str,
    company_name: str,
    market: str,
    min_return_pct: float,
    max_drop_pct: float,
    stooq_symbol: Optional[str] = None,
    notes: str = "",
    workspace_id: int | None = None,
) -> None:
    workspace_id = workspace_id or get_user_workspace_id(db_path, user_id)
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO stocks (user_id, workspace_id, symbol, company_name, market, stooq_symbol, min_return_pct, max_drop_pct, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                workspace_id,
                symbol.upper(),
                company_name,
                market,
                stooq_symbol,
                float(min_return_pct),
                float(max_drop_pct),
                notes,
            ),
        )


def delete_stock(db_path: Path, user_id: int, stock_id: int, workspace_id: int | None = None) -> None:
    workspace_id = workspace_id or get_user_workspace_id(db_path, user_id)
    with connect(db_path) as conn:
        conn.execute(
            "DELETE FROM stocks WHERE id = ? AND user_id = ? AND workspace_id = ?",
            (stock_id, user_id, workspace_id),
        )


def add_report(
    db_path: Path,
    user_id: int,
    report_date: str,
    path: str,
    workspace_id: int | None = None,
) -> None:
    workspace_id = workspace_id or get_user_workspace_id(db_path, user_id)
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO reports (user_id, workspace_id, report_date, path)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, workspace_id, report_date, path),
        )


def list_reports(db_path: Path, user_id: int, workspace_id: int | None = None) -> List[Report]:
    workspace_id = workspace_id or get_user_workspace_id(db_path, user_id)
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM reports
            WHERE user_id = ? AND workspace_id = ?
            ORDER BY report_date DESC
            """,
            (user_id, workspace_id),
        ).fetchall()
    return [
        Report(
            id=int(row["id"]),
            user_id=int(row["user_id"]),
            workspace_id=int(row["workspace_id"] or 0),
            report_date=str(row["report_date"]),
            path=str(row["path"]),
        )
        for row in rows
    ]


def _build_run(row: sqlite3.Row) -> Run:
    return Run(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        workspace_id=int(row["workspace_id"] or 0),
        status=str(row["status"]),
        started_at=str(row["started_at"] or ""),
        finished_at=str(row["finished_at"] or ""),
        report_date=str(row["report_date"] or ""),
        message=str(row["message"] or ""),
        progress=int(row["progress"] or 0),
    )


def create_run(db_path: Path, user_id: int, workspace_id: int | None = None) -> Run:
    workspace_id = workspace_id or get_user_workspace_id(db_path, user_id)
    with connect(db_path) as conn:
        result = conn.execute(
            "INSERT INTO runs (user_id, workspace_id, status, progress, message) VALUES (?, ?, ?, ?, ?)",
            (user_id, workspace_id, "QUEUED", 0, "Queued"),
        )
        run_id = int(result.lastrowid)
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    return _build_run(row)


def enqueue_run_job(db_path: Path, user_id: int, workspace_id: int | None = None) -> Run:
    workspace_id = workspace_id or get_user_workspace_id(db_path, user_id)
    with connect(db_path) as conn:
        result = conn.execute(
            "INSERT INTO runs (user_id, workspace_id, status, progress, message) VALUES (?, ?, ?, ?, ?)",
            (user_id, workspace_id, "QUEUED", 0, "Queued"),
        )
        run_id = int(result.lastrowid)
        conn.execute(
            """
            INSERT INTO job_queue (run_id, user_id, workspace_id, status, attempts, available_at)
            VALUES (?, ?, ?, 'QUEUED', 0, datetime('now'))
            """,
            (run_id, user_id, workspace_id),
        )
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    return _build_run(row)


def claim_next_job(db_path: Path) -> Job | None:
    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT *
            FROM job_queue
            WHERE status = 'QUEUED' AND available_at <= datetime('now')
            ORDER BY id
            LIMIT 1
            """,
        ).fetchone()
        if row is None:
            return None
        job_id = int(row["id"])
        conn.execute(
            """
            UPDATE job_queue
            SET status = 'RUNNING',
                attempts = attempts + 1,
                locked_at = datetime('now'),
                updated_at = datetime('now'),
                error = NULL
            WHERE id = ? AND status = 'QUEUED'
            """,
            (job_id,),
        )
        updated = conn.execute("SELECT * FROM job_queue WHERE id = ?", (job_id,)).fetchone()
        if updated is None or updated["status"] != "RUNNING":
            return None
        return Job(
            id=int(updated["id"]),
            run_id=int(updated["run_id"]),
            user_id=int(updated["user_id"]),
            workspace_id=int(updated["workspace_id"] or 0),
            status=str(updated["status"]),
            attempts=int(updated["attempts"] or 0),
            available_at=str(updated["available_at"] or ""),
            locked_at=str(updated["locked_at"] or ""),
            error=str(updated["error"] or ""),
        )


def mark_job_done(db_path: Path, job_id: int) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE job_queue
            SET status = 'DONE', updated_at = datetime('now')
            WHERE id = ?
            """,
            (job_id,),
        )


def mark_job_retry(db_path: Path, job_id: int, error: str, backoff_seconds: int) -> None:
    delay = f"+{max(1, int(backoff_seconds))} seconds"
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE job_queue
            SET status = 'QUEUED',
                available_at = datetime('now', ?),
                locked_at = NULL,
                error = ?,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (delay, error[:500], job_id),
        )


def mark_job_failed(db_path: Path, job_id: int, error: str) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE job_queue
            SET status = 'FAILED',
                error = ?,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (error[:500], job_id),
        )


def update_run(
    db_path: Path,
    run_id: int,
    status: str,
    report_date: str | None = None,
    message: str | None = None,
) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE runs
            SET status = ?,
                finished_at = datetime('now'),
                report_date = ?,
                message = ?,
                progress = CASE WHEN ? = 'FAILED' THEN progress ELSE 100 END
            WHERE id = ?
            """,
            (status, report_date, message, status, run_id),
        )


def update_run_progress(
    db_path: Path,
    run_id: int,
    status: str | None = None,
    message: str | None = None,
    progress: int | None = None,
) -> None:
    fields = []
    params = []
    if status is not None:
        fields.append("status = ?")
        params.append(status)
    if message is not None:
        fields.append("message = ?")
        params.append(message)
    if progress is not None:
        safe = max(0, min(99, int(progress)))
        fields.append("progress = ?")
        params.append(safe)
    if not fields:
        return
    sql = f"UPDATE runs SET {', '.join(fields)} WHERE id = ?"
    params.append(run_id)
    with connect(db_path) as conn:
        conn.execute(sql, params)


def list_runs(db_path: Path, user_id: int, workspace_id: int | None = None) -> List[Run]:
    workspace_id = workspace_id or get_user_workspace_id(db_path, user_id)
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM runs
            WHERE user_id = ? AND workspace_id = ?
            ORDER BY started_at DESC
            """,
            (user_id, workspace_id),
        ).fetchall()
    return [_build_run(row) for row in rows]


def get_latest_run(db_path: Path, user_id: int, workspace_id: int | None = None) -> Run | None:
    workspace_id = workspace_id or get_user_workspace_id(db_path, user_id)
    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT *
            FROM runs
            WHERE user_id = ? AND workspace_id = ?
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (user_id, workspace_id),
        ).fetchone()
    if row is None:
        return None
    return _build_run(row)


def create_trade_intent(
    db_path: Path,
    user_id: int,
    workspace_id: int,
    run_id: int,
    symbol: str,
    side: str,
    reference_price: float,
    expected_return_pct: float,
    confidence_pct: float,
    reasoning: str,
    quantity: float = 1.0,
    mode: str = "PAPER",
) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO trades (
                user_id, workspace_id, run_id, symbol, side, quantity,
                reference_price, status, mode, confidence_pct,
                expected_return_pct, reasoning
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?, ?, ?)
            """,
            (
                user_id,
                workspace_id,
                run_id,
                symbol.upper(),
                side.upper(),
                float(quantity),
                float(reference_price),
                mode,
                float(confidence_pct),
                float(expected_return_pct),
                reasoning,
            ),
        )


def list_trades(
    db_path: Path,
    user_id: int,
    workspace_id: int | None = None,
    status: str | None = None,
    limit: int = 100,
) -> List[Trade]:
    workspace_id = workspace_id or get_user_workspace_id(db_path, user_id)
    with connect(db_path) as conn:
        if status:
            rows = conn.execute(
                """
                SELECT *
                FROM trades
                WHERE user_id = ? AND workspace_id = ? AND status = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, workspace_id, status.upper(), limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT *
                FROM trades
                WHERE user_id = ? AND workspace_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, workspace_id, limit),
            ).fetchall()
    return [
        Trade(
            id=int(row["id"]),
            user_id=int(row["user_id"]),
            workspace_id=int(row["workspace_id"] or 0),
            run_id=int(row["run_id"] or 0),
            symbol=str(row["symbol"]),
            side=str(row["side"]),
            quantity=float(row["quantity"] or 0),
            reference_price=float(row["reference_price"] or 0),
            executed_price=float(row["executed_price"] or 0),
            status=str(row["status"]),
            mode=str(row["mode"]),
            confidence_pct=float(row["confidence_pct"] or 0),
            expected_return_pct=float(row["expected_return_pct"] or 0),
            reasoning=str(row["reasoning"] or ""),
            approved_at=str(row["approved_at"] or ""),
            executed_at=str(row["executed_at"] or ""),
            notes=str(row["notes"] or ""),
        )
        for row in rows
    ]


def get_trade_by_id(db_path: Path, user_id: int, trade_id: int) -> Trade | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM trades WHERE id = ? AND user_id = ?",
            (trade_id, user_id),
        ).fetchone()
    if row is None:
        return None
    return Trade(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        workspace_id=int(row["workspace_id"] or 0),
        run_id=int(row["run_id"] or 0),
        symbol=str(row["symbol"]),
        side=str(row["side"]),
        quantity=float(row["quantity"] or 0),
        reference_price=float(row["reference_price"] or 0),
        executed_price=float(row["executed_price"] or 0),
        status=str(row["status"]),
        mode=str(row["mode"]),
        confidence_pct=float(row["confidence_pct"] or 0),
        expected_return_pct=float(row["expected_return_pct"] or 0),
        reasoning=str(row["reasoning"] or ""),
        approved_at=str(row["approved_at"] or ""),
        executed_at=str(row["executed_at"] or ""),
        notes=str(row["notes"] or ""),
    )


def approve_trade(db_path: Path, user_id: int, trade_id: int) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE trades
            SET status = 'APPROVED', approved_at = datetime('now')
            WHERE id = ? AND user_id = ? AND status = 'PENDING'
            """,
            (trade_id, user_id),
        )


def reject_trade(db_path: Path, user_id: int, trade_id: int, note: str = "") -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE trades
            SET status = 'REJECTED', notes = ?
            WHERE id = ? AND user_id = ? AND status IN ('PENDING', 'APPROVED')
            """,
            (note[:500], trade_id, user_id),
        )


def execute_trade(db_path: Path, user_id: int, trade_id: int, executed_price: float) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE trades
            SET status = 'EXECUTED',
                executed_price = ?,
                executed_at = datetime('now')
            WHERE id = ? AND user_id = ? AND status = 'APPROVED'
            """,
            (float(executed_price), trade_id, user_id),
        )


def record_model_metric(
    db_path: Path,
    user_id: int,
    workspace_id: int,
    symbol: str,
    horizon: str,
    model_name: str,
    mape: float,
    rmse: float,
    selected: int = 0,
) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO model_metrics (
                user_id, workspace_id, symbol, horizon, model_name, mape, rmse, selected
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                workspace_id,
                symbol.upper(),
                horizon,
                model_name,
                float(mape),
                float(rmse),
                int(selected),
            ),
        )


def list_model_metrics(
    db_path: Path,
    user_id: int,
    workspace_id: int | None = None,
    limit: int = 200,
) -> List[ModelMetric]:
    workspace_id = workspace_id or get_user_workspace_id(db_path, user_id)
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM model_metrics
            WHERE user_id = ? AND workspace_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, workspace_id, limit),
        ).fetchall()
    return [
        ModelMetric(
            id=int(row["id"]),
            user_id=int(row["user_id"]),
            workspace_id=int(row["workspace_id"] or 0),
            symbol=str(row["symbol"]),
            horizon=str(row["horizon"]),
            model_name=str(row["model_name"]),
            mape=float(row["mape"]),
            rmse=float(row["rmse"]),
            selected=int(row["selected"] or 0),
            created_at=str(row["created_at"] or ""),
        )
        for row in rows
    ]


def _build_model_profile(row: sqlite3.Row) -> ModelProfile:
    return ModelProfile(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        workspace_id=int(row["workspace_id"] or 0),
        symbol=str(row["symbol"]),
        horizon=str(row["horizon"]),
        preferred_model=str(row["preferred_model"]),
        last_mape=float(row["last_mape"] or 0.0),
        last_rmse=float(row["last_rmse"] or 0.0),
        sample_count=int(row["sample_count"] or 0),
        last_trained_at=str(row["last_trained_at"] or ""),
    )


def get_model_profile(
    db_path: Path,
    user_id: int,
    workspace_id: int,
    symbol: str,
    horizon: str,
) -> ModelProfile | None:
    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT *
            FROM model_profiles
            WHERE user_id = ? AND workspace_id = ? AND symbol = ? AND horizon = ?
            LIMIT 1
            """,
            (user_id, workspace_id, symbol.upper(), horizon),
        ).fetchone()
    if row is None:
        return None
    return _build_model_profile(row)


def upsert_model_profile(
    db_path: Path,
    user_id: int,
    workspace_id: int,
    symbol: str,
    horizon: str,
    preferred_model: str,
    last_mape: float,
    last_rmse: float,
) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO model_profiles (
                user_id, workspace_id, symbol, horizon,
                preferred_model, last_mape, last_rmse, sample_count, last_trained_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, datetime('now'), datetime('now'))
            ON CONFLICT(user_id, workspace_id, symbol, horizon)
            DO UPDATE SET
                preferred_model = excluded.preferred_model,
                last_mape = excluded.last_mape,
                last_rmse = excluded.last_rmse,
                sample_count = model_profiles.sample_count + 1,
                last_trained_at = datetime('now'),
                updated_at = datetime('now')
            """,
            (
                user_id,
                workspace_id,
                symbol.upper(),
                horizon,
                preferred_model,
                float(last_mape),
                float(last_rmse),
            ),
        )


def list_model_profiles(
    db_path: Path,
    user_id: int,
    workspace_id: int,
    limit: int = 500,
) -> List[ModelProfile]:
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM model_profiles
            WHERE user_id = ? AND workspace_id = ?
            ORDER BY last_trained_at DESC
            LIMIT ?
            """,
            (user_id, workspace_id, limit),
        ).fetchall()
    return [_build_model_profile(row) for row in rows]


def increment_metric(db_path: Path, metric_name: str, metric_value: float = 1.0, tags: str = "") -> None:
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO app_metrics (metric_name, metric_value, tags) VALUES (?, ?, ?)",
            (metric_name, float(metric_value), tags[:500]),
        )


def db_health(db_path: Path) -> bool:
    try:
        with connect(db_path) as conn:
            conn.execute("SELECT 1").fetchone()
        return True
    except Exception:
        return False


def queue_stats(db_path: Path) -> dict:
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT status, COUNT(*) AS c
            FROM job_queue
            GROUP BY status
            """
        ).fetchall()
    stats = {"QUEUED": 0, "RUNNING": 0, "DONE": 0, "FAILED": 0}
    for row in rows:
        stats[str(row["status"])] = int(row["c"])
    return stats
