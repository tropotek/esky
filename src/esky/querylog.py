import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class QueryEntry:
    query: str
    tags: list[str]
    returned_count: int
    matched_count: int | None
    top_uid: str | None
    created_at: str


def log_query(conn: sqlite3.Connection, query: str, hits,
              matched: int | None = None,
              tags: list[str] | None = None) -> None:
    """Record one search and what it found.

    Kept in the profile database rather than a log file so it inherits profile
    isolation, the backup story and the same tooling: a query about the work
    store must not be readable through the personal one.

    `matched` is how many facts the search found before `limit` truncated it.
    Without it a query that matched plenty is indistinguishable from one that
    matched nothing, since the stored count can be no larger than the limit.
    It is optional, and a caller that cannot supply it leaves NULL rather than
    a guess.

    Failures are not swallowed. This is one INSERT into a local table, so the
    only way it fails is a database that is already broken — and hiding that
    behind a successful search would make the store lie about its own health.
    """
    top = hits[0].uid if hits else None
    conn.execute(
        "INSERT INTO queries(query, tags, returned_count, matched_count, "
        "top_uid, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (query, json.dumps(list(tags or [])), len(hits), matched, top,
         datetime.now(UTC).isoformat()),
    )


def recent_queries(conn: sqlite3.Connection, limit: int = 50) -> list[QueryEntry]:
    """Most recent searches first, which is the order they are read in."""
    rows = conn.execute(
        "SELECT query, tags, returned_count, matched_count, top_uid, "
        "created_at FROM queries "
        "ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [
        QueryEntry(query=r["query"], tags=json.loads(r["tags"]),
                   returned_count=r["returned_count"],
                   matched_count=r["matched_count"],
                   top_uid=r["top_uid"], created_at=r["created_at"])
        for r in rows
    ]
