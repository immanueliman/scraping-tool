"""Self-contained SQLite storage (no external dependency)."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS contacts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE,
    company       TEXT,
    domain        TEXT,
    role          TEXT NOT NULL DEFAULT 'other',
    full_name     TEXT,
    title         TEXT,
    phone         TEXT,
    linkedin      TEXT,
    grade         TEXT,
    grade_label   TEXT,
    function      TEXT,
    rank_score    INTEGER DEFAULT 0,
    industry      TEXT,
    verify        TEXT NOT NULL DEFAULT 'unknown',
    source        TEXT,
    status        TEXT NOT NULL DEFAULT 'new',
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS suppression (
    email         TEXT PRIMARY KEY,
    reason        TEXT,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_contacts_role   ON contacts(role);
CREATE INDEX IF NOT EXISTS idx_contacts_verify ON contacts(verify);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")     # concurrent read while writing
    conn.execute("PRAGMA busy_timeout = 30000")   # wait for locks, don't error
    return conn


@contextmanager
def session(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init(path: Path | None = None) -> Path:
    target = path or DB_PATH
    with session(target) as conn:
        conn.executescript(SCHEMA)
    return target


def is_suppressed(conn, email: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM suppression WHERE email = ?", (email.lower(),)
    ).fetchone() is not None


def suppress(conn, email: str, reason: str = "sent") -> None:
    email = email.lower()
    conn.execute(
        "INSERT OR REPLACE INTO suppression (email, reason, created_at) VALUES (?,?,?)",
        (email, reason, now()))
    conn.execute("UPDATE contacts SET status = 'sent' WHERE email = ?", (email,))


def upsert_contact(conn, *, email: str, company: str = "", domain: str = "",
                   role: str = "other", full_name: str | None = None,
                   title: str | None = None, phone: str | None = None,
                   linkedin: str | None = None, grade: str | None = None,
                   grade_label: str | None = None, function: str | None = None,
                   rank_score: int = 0, industry: str | None = None,
                   source: str = "") -> int | None:
    """Insert or update a contact. Returns id, or None if suppressed.

    Richer detail (name/title/grade/rank) overwrites when a new pass finds it —
    a named-person hit should upgrade a bare-mailbox row for the same address.
    """
    email = email.lower().strip()
    if is_suppressed(conn, email):
        return None
    row = conn.execute("SELECT id, rank_score FROM contacts WHERE email = ?", (email,)).fetchone()
    if row:
        # keep the higher-grade record if a later pass found a named person
        keep_rank = max(int(row["rank_score"] or 0), rank_score)
        conn.execute(
            "UPDATE contacts SET company = COALESCE(NULLIF(?,''), company), "
            "domain = COALESCE(NULLIF(?,''), domain), "
            "role = CASE WHEN role = 'other' THEN ? ELSE role END, "
            "full_name = COALESCE(?, full_name), title = COALESCE(?, title), "
            "phone = COALESCE(NULLIF(?,''), phone), linkedin = COALESCE(NULLIF(?,''), linkedin), "
            "grade = COALESCE(?, grade), grade_label = COALESCE(?, grade_label), "
            "function = COALESCE(?, function), rank_score = ?, "
            "industry = COALESCE(?, industry) WHERE id = ?",
            (company, domain, role, full_name, title, phone, linkedin, grade,
             grade_label, function, keep_rank, industry, row["id"]))
        return int(row["id"])
    cur = conn.execute(
        "INSERT INTO contacts (email, company, domain, role, full_name, title, "
        "phone, linkedin, grade, grade_label, function, rank_score, industry, "
        "source, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (email, company, domain, role, full_name, title, phone, linkedin, grade,
         grade_label, function, rank_score, industry, source, now()))
    return int(cur.lastrowid)


def set_verify(conn, contact_id: int, verify: str) -> None:
    conn.execute("UPDATE contacts SET verify = ? WHERE id = ?", (verify, contact_id))
    if verify == "invalid":
        conn.execute("UPDATE contacts SET status = 'invalid' WHERE id = ?", (contact_id,))
