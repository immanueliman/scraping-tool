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
    location      TEXT,
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
CREATE TABLE IF NOT EXISTS state (
    key           TEXT PRIMARY KEY,
    value         TEXT
);
"""

# Columns beyond (id, email, created_at) — used to migrate an OLD leads.db that
# predates newer columns (CREATE TABLE IF NOT EXISTS cannot add them).
_CONTACT_COLUMNS = {
    "company": "TEXT", "domain": "TEXT", "role": "TEXT DEFAULT 'other'",
    "full_name": "TEXT", "title": "TEXT", "phone": "TEXT", "linkedin": "TEXT",
    "grade": "TEXT", "grade_label": "TEXT", "function": "TEXT",
    "rank_score": "INTEGER DEFAULT 0", "industry": "TEXT", "location": "TEXT",
    "verify": "TEXT DEFAULT 'unknown'", "source": "TEXT", "status": "TEXT DEFAULT 'new'",
}
_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_contacts_role   ON contacts(role)",
    "CREATE INDEX IF NOT EXISTS idx_contacts_verify ON contacts(verify)",
    "CREATE INDEX IF NOT EXISTS idx_contacts_rank   ON contacts(rank_score)",
)


def get_state(conn, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM state WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_state(conn, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO state (key, value) VALUES (?,?)",
                 (key, str(value)))


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
        conn.executescript(SCHEMA)                 # create tables if missing
        # migrate: add any columns an older contacts table is missing…
        have = {r[1] for r in conn.execute("PRAGMA table_info(contacts)")}
        for col, decl in _CONTACT_COLUMNS.items():
            if col not in have:
                conn.execute(f"ALTER TABLE contacts ADD COLUMN {col} {decl}")
        # …then build indexes (safe now that rank_score etc. exist)
        for idx in _INDEXES:
            conn.execute(idx)
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
                   location: str | None = None, source: str = "") -> int | None:
    """Insert or update a contact. Returns id, or None if suppressed.

    Richer detail (name/title/grade/rank) overwrites when a new pass finds it —
    a named-person hit should upgrade a bare-mailbox row for the same address.
    """
    email = email.lower().strip()
    if is_suppressed(conn, email):
        return None
    row = conn.execute(
        "SELECT id, rank_score, grade, grade_label, function FROM contacts "
        "WHERE email = ?", (email,)).fetchone()
    if row:
        # Only let a NEW pass overwrite grade/label/function when it is at least
        # as strong (rank) as what's stored — so a later bare-mailbox sighting
        # can't downgrade a named decision-maker. Name/phone/etc. still enrich.
        existing = int(row["rank_score"] or 0)
        better = rank_score >= existing
        new_grade = grade if better else row["grade"]
        new_label = grade_label if better else row["grade_label"]
        new_fn = function if better else row["function"]
        conn.execute(
            "UPDATE contacts SET company = COALESCE(NULLIF(?,''), company), "
            "domain = COALESCE(NULLIF(?,''), domain), "
            "role = CASE WHEN role = 'other' THEN ? ELSE role END, "
            "full_name = COALESCE(?, full_name), title = COALESCE(?, title), "
            "phone = COALESCE(NULLIF(?,''), phone), linkedin = COALESCE(NULLIF(?,''), linkedin), "
            "grade = ?, grade_label = ?, function = ?, rank_score = ?, "
            "industry = COALESCE(?, industry), "
            "location = COALESCE(NULLIF(?,''), location) WHERE id = ?",
            (company, domain, role, full_name, title, phone, linkedin, new_grade,
             new_label, new_fn, max(existing, rank_score), industry, location, row["id"]))
        return int(row["id"])
    try:
        cur = conn.execute(
            "INSERT INTO contacts (email, company, domain, role, full_name, title, "
            "phone, linkedin, grade, grade_label, function, rank_score, industry, "
            "location, source, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (email, company, domain, role, full_name, title, phone, linkedin, grade,
             grade_label, function, rank_score, industry, location, source, now()))
        return int(cur.lastrowid)
    except sqlite3.IntegrityError:
        # concurrent writer inserted the same email between our SELECT and INSERT
        r2 = conn.execute("SELECT id FROM contacts WHERE email = ?", (email,)).fetchone()
        return int(r2["id"]) if r2 else None


def set_verify(conn, contact_id: int, verify: str) -> None:
    conn.execute("UPDATE contacts SET verify = ? WHERE id = ?", (verify, contact_id))
    if verify == "invalid":
        conn.execute("UPDATE contacts SET status = 'invalid' WHERE id = ?", (contact_id,))
