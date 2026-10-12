"""SQLite database operations."""

import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from shellcron.daemon.models import STATUS_RUNNING, STATUS_SUCCESS, STATUS_FAILED, STATUS_SKIPPED


DB_DIR = Path.home() / ".local" / "share" / "shellcrond"
DB_PATH = DB_DIR / "shelld.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conn() -> sqlite3.Connection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create tables if they don't exist."""
    with _conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS tasks (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            enabled         INTEGER NOT NULL DEFAULT 1,
            schedule_type   TEXT NOT NULL,
            schedule_config TEXT NOT NULL,
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS task_scripts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id     INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            script_path TEXT NOT NULL,
            sort_order  INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS execution_logs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id         INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            triggered_by    TEXT NOT NULL,
            status          TEXT NOT NULL,
            skip_reason     TEXT,
            started_at      TEXT NOT NULL,
            finished_at     TEXT,
            duration_ms     INTEGER,
            created_at      TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS script_results (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            execution_id    INTEGER NOT NULL REFERENCES execution_logs(id) ON DELETE CASCADE,
            script_path     TEXT NOT NULL,
            sort_order      INTEGER NOT NULL,
            return_code     INTEGER,
            stdout          TEXT,
            stderr          TEXT,
            started_at      TEXT NOT NULL,
            finished_at     TEXT,
            duration_ms     INTEGER
        );

        CREATE INDEX IF NOT EXISTS idx_task_scripts_task ON task_scripts(task_id, sort_order);
        CREATE INDEX IF NOT EXISTS idx_exec_logs_task ON execution_logs(task_id, started_at);
        CREATE INDEX IF NOT EXISTS idx_script_results_exec ON script_results(execution_id, sort_order);
        """)


# ── Task CRUD ────────────────────────────────────────────────────

def add_task(name: str, schedule_type: str, schedule_config: str, enabled: bool = True) -> int:
    ts = _now()
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO tasks (name, enabled, schedule_type, schedule_config, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (name, 1 if enabled else 0, schedule_type, schedule_config, ts, ts),
        )
        return cur.lastrowid


def update_task(task_id: int, name: str, schedule_type: str, schedule_config: str, enabled: bool):
    ts = _now()
    with _conn() as conn:
        conn.execute(
            "UPDATE tasks SET name=?, enabled=?, schedule_type=?, schedule_config=?, updated_at=? WHERE id=?",
            (name, 1 if enabled else 0, schedule_type, schedule_config, ts, task_id),
        )


def delete_task(task_id: int):
    """Delete task and cascade scripts + logs."""
    with _conn() as conn:
        conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))


def get_task(task_id: int) -> Optional[dict]:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            return None
        return dict(row)


def get_all_tasks() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM tasks ORDER BY id").fetchall()
        return [dict(r) for r in rows]


def toggle_task(task_id: int, enabled: bool):
    ts = _now()
    with _conn() as conn:
        conn.execute("UPDATE tasks SET enabled=?, updated_at=? WHERE id=?", (1 if enabled else 0, ts, task_id))


# ── Script CRUD ──────────────────────────────────────────────────

def add_script(task_id: int, script_path: str, sort_order: int = 0) -> int:
    ts = _now()
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO task_scripts (task_id, script_path, sort_order, created_at) VALUES (?, ?, ?, ?)",
            (task_id, script_path, sort_order, ts),
        )
        return cur.lastrowid


def remove_script(script_id: int):
    with _conn() as conn:
        conn.execute("DELETE FROM task_scripts WHERE id=?", (script_id,))


def get_task_scripts(task_id: int) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM task_scripts WHERE task_id=? ORDER BY sort_order, id",
            (task_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def reorder_scripts(task_id: int, script_ids: list[int]):
    """Update sort_order for given scripts matching task_id."""
    with _conn() as conn:
        for i, sid in enumerate(script_ids):
            conn.execute(
                "UPDATE task_scripts SET sort_order=? WHERE id=? AND task_id=?",
                (i, sid, task_id),
            )


def set_task_scripts(task_id: int, scripts: list[str]):
    """Replace all scripts for a task with a new ordered list of paths."""
    ts = _now()
    with _conn() as conn:
        conn.execute("DELETE FROM task_scripts WHERE task_id=?", (task_id,))
        for i, path in enumerate(scripts):
            conn.execute(
                "INSERT INTO task_scripts (task_id, script_path, sort_order, created_at) VALUES (?, ?, ?, ?)",
                (task_id, path, i, ts),
            )


# ── Execution Logs ───────────────────────────────────────────────

def create_execution_log(
    task_id: int, triggered_by: str, status: str = STATUS_RUNNING, skip_reason: str = None
) -> int:
    ts = _now()
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO execution_logs (task_id, triggered_by, status, skip_reason, started_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (task_id, triggered_by, status, skip_reason, ts, ts),
        )
        return cur.lastrowid


def update_execution_log(log_id: int, status: str, duration_ms: int = None):
    ts = _now()
    with _conn() as conn:
        conn.execute(
            "UPDATE execution_logs SET status=?, finished_at=?, duration_ms=? WHERE id=?",
            (status, ts, duration_ms, log_id),
        )


def get_execution_logs(task_id: int, limit: int = 50, offset: int = 0) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM execution_logs WHERE task_id=? ORDER BY started_at DESC LIMIT ? OFFSET ?",
            (task_id, limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]


def get_execution_log(log_id: int) -> Optional[dict]:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM execution_logs WHERE id=?", (log_id,)).fetchone()
        return dict(row) if row else None


def get_latest_execution_log(task_id: int) -> Optional[dict]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM execution_logs WHERE task_id=? ORDER BY started_at DESC LIMIT 1",
            (task_id,),
        ).fetchone()
        return dict(row) if row else None


def get_latest_successful_finish(task_id: int) -> Optional[str]:
    """Return ISO timestamp of most recent successful finish, or None."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT finished_at FROM execution_logs "
            "WHERE task_id=? AND status=? AND finished_at IS NOT NULL "
            "ORDER BY finished_at DESC LIMIT 1",
            (task_id, STATUS_SUCCESS),
        ).fetchone()
        return row["finished_at"] if row else None


# ── Script Results ───────────────────────────────────────────────

def add_script_result(
    execution_id: int,
    script_path: str,
    sort_order: int,
    return_code: int = None,
    stdout: str = None,
    stderr: str = None,
    started_at: str = None,
    finished_at: str = None,
    duration_ms: int = None,
) -> int:
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO script_results (execution_id, script_path, sort_order, return_code, stdout, stderr, started_at, finished_at, duration_ms) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (execution_id, script_path, sort_order, return_code, stdout, stderr, started_at, finished_at, duration_ms),
        )
        return cur.lastrowid


def get_script_results(execution_id: int) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM script_results WHERE execution_id=? ORDER BY sort_order",
            (execution_id,),
        ).fetchall()
        return [dict(r) for r in rows]


# ── Cleanup ──────────────────────────────────────────────────────

def get_success_count(task_id: int) -> int:
    """Return number of successful executions for a task."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM execution_logs WHERE task_id=? AND status=?",
            (task_id, STATUS_SUCCESS),
        ).fetchone()
        return row["cnt"] if row else 0


def get_failed_count(task_id: int) -> int:
    """Return number of failed executions for a task."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM execution_logs WHERE task_id=? AND status=?",
            (task_id, STATUS_FAILED),
        ).fetchone()
        return row["cnt"] if row else 0


def cleanup_old_logs(before: str, task_id: int = None):
    """Delete execution logs older than given ISO timestamp."""
    with _conn() as conn:
        if task_id:
            conn.execute(
                "DELETE FROM execution_logs WHERE task_id=? AND started_at<?",
                (task_id, before),
            )
        else:
            conn.execute("DELETE FROM execution_logs WHERE started_at<?", (before,))


def drop_all():
    """Drop all shelld tables (for uninstall)."""
    with _conn() as conn:
        conn.executescript("""
        DROP TABLE IF EXISTS script_results;
        DROP TABLE IF EXISTS execution_logs;
        DROP TABLE IF EXISTS task_scripts;
        DROP TABLE IF EXISTS tasks;
        """)



