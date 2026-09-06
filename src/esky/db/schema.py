import sqlite3

from esky.config import EMBED_DIM

SCHEMA_VERSION = 1

_V1 = f"""
CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS facts (
  id          INTEGER PRIMARY KEY,
  uid         TEXT UNIQUE NOT NULL,
  text        TEXT NOT NULL,
  kind        TEXT NOT NULL,
  tags        TEXT NOT NULL DEFAULT '[]',
  source      TEXT NOT NULL,
  confidence  REAL NOT NULL DEFAULT 1.0,
  supersedes  TEXT,
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL,
  retired_at  TEXT
);

CREATE INDEX IF NOT EXISTS facts_live ON facts(retired_at, updated_at DESC);

CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(text, tags);

CREATE VIRTUAL TABLE IF NOT EXISTS facts_vec USING vec0(
  fact_id INTEGER PRIMARY KEY,
  embedding FLOAT[{EMBED_DIM}]
);
"""


def migrate(conn: sqlite3.Connection) -> None:
    """Bring a profile database up to SCHEMA_VERSION. Idempotent."""
    conn.executescript(_V1)
    conn.execute(
        "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (str(SCHEMA_VERSION),),
    )
