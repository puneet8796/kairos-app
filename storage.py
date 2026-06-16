"""
storage.py
Persistent, anonymous storage for Kairos.

Stores no identifying information. Only: a self-chosen session code, a timestamp,
the analysis result, the transcript, and optional feedback.

Two backends, auto-selected:
  - Neon / Postgres  when DATABASE_URL is set   (the public deployment)
  - local SQLite      otherwise                  (the Mac Mini, where words stay put)

The public API is identical across both. Set DATABASE_URL in the Streamlit secrets
panel as a top-level key to use Neon. Leave it unset to use SQLite. Use the POOLED
Neon connection string (the host with '-pooler' in it), because Streamlit reruns
open many short-lived connections.

Failures never crash the analysis flow. Writes fail soft and log. Lookups raise
StorageError so the app can tell 'no history' apart from 'something broke'.
"""

import json
import logging
import os
import secrets as _secrets
import uuid
from datetime import datetime, timezone

logger = logging.getLogger("kairos.storage")

# --------------------------------------------------------------------------- config
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
_USE_PG = DATABASE_URL.startswith("postgres")
SQLITE_PATH = os.environ.get("KAIROS_DB_PATH", "kairos_sessions.db")

# Code alphabet excludes look-alike characters (no I, L, O, 0, 1) so codes are
# easy to read aloud and retype. 30 ^ 8 = ~6.5e11 combinations.
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_CODE_LEN = 8
_VALID_RATINGS = {"nailed", "partly", "missed"}

_READ_COLUMNS = (
    "read_id, code, created_at, mode, persona, blend, signals, "
    "insight, next_move, honest_question, transcript, locked, "
    "feedback_rating, feedback_text"
)

_initialized = False


class StorageError(Exception):
    """Raised when a storage operation fails in a way the caller should surface."""


# --------------------------------------------------------------------------- connection
def _connect():
    if _USE_PG:
        import psycopg
        return psycopg.connect(DATABASE_URL)
    import sqlite3
    return sqlite3.connect(SQLITE_PATH)


def _adapt(sql: str) -> str:
    """SQL is written with '?' placeholders. Postgres wants '%s'."""
    return sql.replace("?", "%s") if _USE_PG else sql


def _run(conn, sql, params=(), fetch=None):
    """Execute one statement. fetch in {None, 'one', 'all'}. Rows come back as dicts."""
    cur = conn.cursor()
    cur.execute(_adapt(sql), params)
    if fetch is None:
        return None
    cols = [d[0] for d in cur.description]
    if fetch == "one":
        row = cur.fetchone()
        return dict(zip(cols, row)) if row else None
    return [dict(zip(cols, r)) for r in cur.fetchall()]


# --------------------------------------------------------------------------- schema
def init_db():
    """Create the table and index if absent. Portable across SQLite and Postgres."""
    conn = _connect()
    try:
        _run(conn, """
            CREATE TABLE IF NOT EXISTS reads (
                read_id         TEXT PRIMARY KEY,
                code            TEXT NOT NULL,
                created_at      TEXT NOT NULL,
                mode            TEXT NOT NULL DEFAULT 'professional',
                persona         TEXT,
                blend           TEXT,
                signals         TEXT,
                insight         TEXT,
                next_move       TEXT,
                honest_question TEXT,
                transcript      TEXT,
                locked          INTEGER NOT NULL DEFAULT 0,
                feedback_rating TEXT,
                feedback_text   TEXT,
                schema_version  INTEGER NOT NULL DEFAULT 1
            )
        """)
        _run(conn, "CREATE INDEX IF NOT EXISTS idx_reads_code ON reads (code, created_at)")
        conn.commit()
    finally:
        conn.close()


def _ensure_init():
    """Run init_db once per process. Flag flips before the call to avoid recursion."""
    global _initialized
    if _initialized:
        return
    _initialized = True
    try:
        init_db()
    except Exception:
        _initialized = False
        logger.exception("storage: init_db failed")
        raise


# --------------------------------------------------------------------------- codes
def _random_code() -> str:
    return "KQ-" + "".join(_secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LEN))


def code_exists(code: str) -> bool:
    _ensure_init()
    conn = _connect()
    try:
        row = _run(conn, "SELECT 1 FROM reads WHERE code = ? LIMIT 1", (code,), fetch="one")
        return row is not None
    finally:
        conn.close()


def generate_code() -> str:
    """Make a fresh, collision-checked session code: 'KQ-XXXXXXXX'.

    If the database is unreachable, return an unchecked code so the session can
    still proceed. At this code space, collision risk is negligible.
    """
    try:
        _ensure_init()
        for _ in range(5):
            code = _random_code()
            if not code_exists(code):
                return code
    except Exception:
        logger.exception("storage: code collision check unavailable; returning unchecked code")
    return _random_code()


# --------------------------------------------------------------------------- writes
def save_read(
    code: str,
    *,
    mode: str = "professional",
    persona: str = "",
    blend: dict | None = None,
    signals: list | None = None,
    insight: str = "",
    next_move: str = "",
    honest_question: str = "",
    transcript: str = "",
    locked: bool = False,
) -> str | None:
    """Insert one analysis. Returns the new read_id, or None on failure.

    Call this right after analysis with locked=False. Lock it later, when the
    user chooses to save it to their history, via lock_read().
    """
    read_id = uuid.uuid4().hex
    try:
        _ensure_init()
        conn = _connect()
        try:
            _run(conn, """
                INSERT INTO reads
                    (read_id, code, created_at, mode, persona, blend, signals,
                     insight, next_move, honest_question, transcript, locked)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                read_id, code, datetime.now(timezone.utc).isoformat(), mode, persona,
                json.dumps(blend or {}), json.dumps(signals or []),
                insight, next_move, honest_question, transcript, 1 if locked else 0,
            ))
            conn.commit()
        finally:
            conn.close()
        return read_id
    except Exception:
        logger.exception("storage: save_read failed (code=%s)", code)
        return None


def lock_read(read_id: str) -> bool:
    """Mark a read as saved and immutable. Returns True on success."""
    if not read_id:
        return False
    try:
        _ensure_init()
        conn = _connect()
        try:
            _run(conn, "UPDATE reads SET locked = 1 WHERE read_id = ?", (read_id,))
            conn.commit()
        finally:
            conn.close()
        return True
    except Exception:
        logger.exception("storage: lock_read failed (read_id=%s)", read_id)
        return False


def record_feedback(read_id: str, rating: str, text: str = "") -> bool:
    """Attach the one-tap accuracy rating (and optional note) to a read.

    Allowed even on a locked read: feedback is the one thing that may change
    after save, because people give it after seeing the result.
    """
    if not read_id or rating not in _VALID_RATINGS:
        return False
    try:
        _ensure_init()
        conn = _connect()
        try:
            _run(conn,
                 "UPDATE reads SET feedback_rating = ?, feedback_text = ? WHERE read_id = ?",
                 (rating, text or "", read_id))
            conn.commit()
        finally:
            conn.close()
        return True
    except Exception:
        logger.exception("storage: record_feedback failed (read_id=%s)", read_id)
        return False


# --------------------------------------------------------------------------- reads
def _hydrate(row):
    if row is None:
        return None
    row["blend"] = json.loads(row.get("blend") or "{}")
    row["signals"] = json.loads(row.get("signals") or "[]")
    row["locked"] = bool(row.get("locked"))
    return row


def get_thread(code: str) -> list:
    """Return a user's saved reads for a code, oldest first.

    Raises StorageError if the lookup itself fails, so the app can distinguish
    'no history' from 'something broke'.
    """
    if not code:
        return []
    try:
        _ensure_init()
        conn = _connect()
        try:
            rows = _run(conn,
                        f"SELECT {_READ_COLUMNS} FROM reads "
                        "WHERE code = ? AND locked = 1 ORDER BY created_at",
                        (code,), fetch="all")
        finally:
            conn.close()
        return [_hydrate(r) for r in rows]
    except Exception as e:
        logger.exception("storage: get_thread failed (code=%s)", code)
        raise StorageError("Could not look up that code. Please try again.") from e


def get_read(read_id: str):
    """Fetch a single read by id, for the PDF or a detail view."""
    if not read_id:
        return None
    try:
        _ensure_init()
        conn = _connect()
        try:
            row = _run(conn,
                       f"SELECT {_READ_COLUMNS} FROM reads WHERE read_id = ?",
                       (read_id,), fetch="one")
        finally:
            conn.close()
        return _hydrate(row)
    except Exception as e:
        logger.exception("storage: get_read failed (read_id=%s)", read_id)
        raise StorageError("Could not load that entry.") from e


def get_session_count() -> int:
    """Total reads stored. Cheap on Postgres. Used for light analytics."""
    try:
        _ensure_init()
        conn = _connect()
        try:
            row = _run(conn, "SELECT COUNT(*) AS n FROM reads", fetch="one")
        finally:
            conn.close()
        return int(row["n"]) if row else 0
    except Exception:
        logger.exception("storage: get_session_count failed")
        return 0


# --------------------------------------------------------------------------- transitional
def save_session(token, mode, persona, blend, transcript, insight):
    """Deprecated shim for the pre-memory app. Saves a locked read so the current
    app keeps running until app.py adopts save_read / lock_read. Remove after."""
    return save_read(
        token, mode=mode, persona=persona, blend=blend,
        insight=insight, transcript=transcript, locked=True,
    )
