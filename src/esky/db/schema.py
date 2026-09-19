import sqlite3

from esky.config import EMBED_DIM

SCHEMA_VERSION = 4

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

# fts5 has no ALTER, so gaining a column means rebuilding the table. That is
# safe: the FTS index is derived data. The vector index is not rebuilt here —
# its embeddings can only be recomputed in Python — and it needs no change.
_V2 = """
ALTER TABLE facts ADD COLUMN title TEXT;

DROP TABLE facts_fts;
CREATE VIRTUAL TABLE facts_fts USING fts5(title, text, tags);

INSERT INTO facts_fts(rowid, title, text, tags)
SELECT id, coalesce(title, ''), text,
       (SELECT group_concat(value, ' ') FROM json_each(facts.tags))
FROM facts WHERE retired_at IS NULL;
"""

# Two additions. Retirement gains a reason: `memory_forget` already accepted
# one and dropped it on the floor, so the tool promised a record the store did
# not keep. And `queries` logs what was asked of memory — a search that found
# nothing is the signal for what belongs in the store, and it is unrecoverable
# unless it is written down when it happens.
_V3 = """
ALTER TABLE facts ADD COLUMN retired_reason TEXT;

CREATE TABLE IF NOT EXISTS queries (
  id          INTEGER PRIMARY KEY,
  query       TEXT NOT NULL,
  tags        TEXT NOT NULL DEFAULT '[]',
  hits        INTEGER NOT NULL,
  top_uid     TEXT,
  created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS queries_recent ON queries(id DESC);
"""

# `hits` said only how many rows the caller was handed, which is bounded by its
# `limit` — so a query that matched plenty and one that matched nothing could
# both read as a small number. Splitting the two makes the distinction legible,
# and existing rows keep an unknown `matched_count` rather than a wrong one.
#
# The index goes: `queries.id` is INTEGER PRIMARY KEY, hence the rowid, and
# SQLite already walks it backwards for `ORDER BY id DESC`.
_V4 = """
DROP INDEX IF EXISTS queries_recent;

ALTER TABLE queries RENAME COLUMN hits TO returned_count;
ALTER TABLE queries ADD COLUMN matched_count INTEGER;
"""


def _version(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    return int(row[0]) if row else 0


def migrate(conn: sqlite3.Connection) -> None:
    """Bring a profile database up to SCHEMA_VERSION. Idempotent.

    Step 1 is the full schema and is written to be re-runnable; later steps
    are one-way, so they are applied only to databases below their version.
    """
    conn.executescript(_V1)
    version = _version(conn)
    if version < 2:
        conn.executescript(_V2)
    if version < 3:
        conn.executescript(_V3)
    if version < 4:
        conn.executescript(_V4)
    conn.execute(
        "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (str(SCHEMA_VERSION),),
    )
    conn.commit()
