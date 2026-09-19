"""Aggregates over a profile: what was asked of memory, and what it holds.

Read-only, and deliberately computed in SQL over the whole window rather than
from the newest N rows `/queries` hands back. A chart drawn from a truncated
list quietly answers a different question than the one it is labelled with.

Timestamps are ISO-8601 UTC strings, so a day is the first ten characters and
grouping needs no date parsing in SQL. `now` is a parameter because every
figure here is relative to it, and a test cannot assert on a moving today.
"""

import json
import sqlite3
from datetime import UTC, date, datetime, timedelta

# Chosen so the common shapes are distinguishable: nothing, thin, a normal
# answer, and more than an agent will read.
_BUCKETS = (
    ("0", 0, 0),
    ("1-2", 1, 2),
    ("3-5", 3, 5),
    ("6-10", 6, 10),
    ("11+", 11, None),
)


def _today(now: str | None) -> date:
    if now is None:
        return datetime.now(UTC).date()
    return datetime.fromisoformat(now).astimezone(UTC).date()


def _window(days: int, now: str | None) -> tuple[date, date]:
    """The last `days` days ending today, inclusive of both ends."""
    end = _today(now)
    return end - timedelta(days=days - 1), end


def _dates(start: date, end: date) -> list[str]:
    span = (end - start).days
    return [(start + timedelta(days=i)).isoformat() for i in range(span + 1)]


def _bucket(matched: int | None) -> str:
    if matched is None:
        return "unknown"
    for label, low, high in _BUCKETS:
        if matched >= low and (high is None or matched <= high):
            return label
    return "unknown"


def _tag_counts(rows, top: int) -> list[dict]:
    """Count tags one row at a time.

    Tags live as a JSON array in a text column, so this counts in Python. The
    alternative, `json_each` in a join, is more SQL for no gain at these sizes.
    """
    counts: dict[str, int] = {}
    for raw in rows:
        for tag in json.loads(raw or "[]"):
            counts[tag] = counts.get(tag, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [{"tag": t, "count": c} for t, c in ranked[:top]]


def query_summary(conn: sqlite3.Connection, days: int = 30, top: int = 10,
                  now: str | None = None) -> dict:
    """What memory was asked in the window, and how often it could answer.

    `zero_match` counts searches that handed the agent nothing, which is
    readable from `returned_count` on every row. `matched_count` is finer but
    is NULL on rows written before it existed, so those are reported as
    `unknown_matched` rather than folded into either side.
    """
    start, end = _window(days, now)
    lo, hi = start.isoformat(), end.isoformat() + "￿"

    totals = conn.execute(
        "SELECT count(*) AS searches, "
        "       sum(returned_count = 0) AS zero_match, "
        "       sum(matched_count IS NULL) AS unknown_matched, "
        "       count(DISTINCT query) AS distinct_queries "
        "FROM queries WHERE created_at BETWEEN ? AND ?", (lo, hi)).fetchone()

    per_day = {
        r["day"]: {"searches": r["searches"], "zero_match": r["zero_match"]}
        for r in conn.execute(
            "SELECT substr(created_at, 1, 10) AS day, count(*) AS searches, "
            "       sum(returned_count = 0) AS zero_match "
            "FROM queries WHERE created_at BETWEEN ? AND ? "
            "GROUP BY day", (lo, hi))
    }
    daily = [{"date": d,
              "searches": per_day.get(d, {}).get("searches", 0),
              "zero_match": per_day.get(d, {}).get("zero_match", 0)}
             for d in _dates(start, end)]

    counts = {label: 0 for label, _, _ in _BUCKETS}
    counts["unknown"] = 0
    for row in conn.execute(
            "SELECT matched_count, count(*) AS n FROM queries "
            "WHERE created_at BETWEEN ? AND ? GROUP BY matched_count", (lo, hi)):
        counts[_bucket(row["matched_count"])] += row["n"]
    match_buckets = [{"label": label, "count": counts[label]}
                     for label, _, _ in _BUCKETS] + \
                    [{"label": "unknown", "count": counts["unknown"]}]

    top_queries = [
        {"query": r["query"], "count": r["n"], "zero_match": r["misses"]}
        for r in conn.execute(
            "SELECT query, count(*) AS n, sum(returned_count = 0) AS misses "
            "FROM queries WHERE created_at BETWEEN ? AND ? "
            "GROUP BY query ORDER BY n DESC, query LIMIT ?", (lo, hi, top))
    ]

    top_tags = _tag_counts(
        (r["tags"] for r in conn.execute(
            "SELECT tags FROM queries WHERE created_at BETWEEN ? AND ?",
            (lo, hi))),
        top)

    top_facts = [
        {"uid": r["top_uid"], "count": r["n"], "title": r["title"]}
        for r in conn.execute(
            "SELECT q.top_uid, count(*) AS n, f.title FROM queries q "
            "LEFT JOIN facts f ON f.uid = q.top_uid "
            "WHERE q.created_at BETWEEN ? AND ? AND q.top_uid IS NOT NULL "
            "GROUP BY q.top_uid ORDER BY n DESC, q.top_uid LIMIT ?",
            (lo, hi, top))
    ]

    return {
        "days": days,
        "from": start.isoformat(),
        "to": end.isoformat(),
        "totals": {
            "searches": totals["searches"],
            "zero_match": totals["zero_match"] or 0,
            "unknown_matched": totals["unknown_matched"] or 0,
            "distinct_queries": totals["distinct_queries"],
        },
        "daily": daily,
        "match_buckets": match_buckets,
        "top_queries": top_queries,
        "top_tags": top_tags,
        "top_facts": top_facts,
    }


def fact_stats(conn: sqlite3.Connection, days: int = 30, top: int = 10,
               now: str | None = None) -> dict:
    """What the store holds: size, mix, and how it grew over the window.

    `facts` and `retired` keep the names the endpoint has always returned;
    everything else is additive, so an older client reading this still works.
    """
    start, end = _window(days, now)
    lo, hi = start.isoformat(), end.isoformat() + "￿"

    counts = conn.execute(
        "SELECT sum(retired_at IS NULL) AS live, "
        "       sum(retired_at IS NOT NULL) AS retired FROM facts").fetchone()

    kinds = [{"kind": r["kind"], "count": r["n"]} for r in conn.execute(
        "SELECT kind, count(*) AS n FROM facts WHERE retired_at IS NULL "
        "GROUP BY kind ORDER BY n DESC, kind")]

    top_tags = _tag_counts(
        (r["tags"] for r in conn.execute(
            "SELECT tags FROM facts WHERE retired_at IS NULL")),
        top)

    created = {r["day"]: r["n"] for r in conn.execute(
        "SELECT substr(created_at, 1, 10) AS day, count(*) AS n FROM facts "
        "WHERE created_at BETWEEN ? AND ? GROUP BY day", (lo, hi))}
    retired = {r["day"]: r["n"] for r in conn.execute(
        "SELECT substr(retired_at, 1, 10) AS day, count(*) AS n FROM facts "
        "WHERE retired_at BETWEEN ? AND ? GROUP BY day", (lo, hi))}
    daily = [{"date": d, "created": created.get(d, 0),
              "retired": retired.get(d, 0)} for d in _dates(start, end)]

    span = conn.execute(
        "SELECT min(created_at) AS oldest, max(created_at) AS newest "
        "FROM facts").fetchone()

    return {
        "facts": counts["live"] or 0,
        "retired": counts["retired"] or 0,
        "days": days,
        "from": start.isoformat(),
        "to": end.isoformat(),
        "kinds": kinds,
        "top_tags": top_tags,
        "daily": daily,
        "oldest": span["oldest"],
        "newest": span["newest"],
    }
