"""
storage.py
Anonymous session storage for Kairos.
Stores no identifying information.
Only: token, timestamp, mode, persona, blend, transcript, insight.
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = os.environ.get("KAIROS_DB_PATH", "kairos_sessions.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            mode TEXT NOT NULL,
            persona TEXT,
            blend TEXT,
            transcript TEXT,
            insight TEXT
        )
    """)
    conn.commit()
    conn.close()


def save_session(
    token: str,
    mode: str,
    persona: str,
    blend: dict,
    transcript: str,
    insight: str,
):
    try:
        init_db()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO sessions
            (token, timestamp, mode, persona, blend, transcript, insight)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                token,
                datetime.utcnow().isoformat(),
                mode,
                persona,
                str(blend),
                transcript,
                insight,
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass  # never block the user for a storage failure


def get_session_count() -> int:
    try:
        init_db()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM sessions")
        count = c.fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0
