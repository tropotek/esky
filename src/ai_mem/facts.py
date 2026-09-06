import json
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Sequence

import sqlite_vec

KINDS = frozenset({"user", "preference", "project", "reference", "decision"})


class InvalidKind(Exception):
    """kind is not one of KINDS."""


class FactNotFound(Exception):
    """No fact with that uid."""


@dataclass(frozen=True)
class Fact:
    uid: str
    text: str
    kind: str
    tags: list[str]
    source: str
    confidence: float
    supersedes: str | None
    created_at: str
    updated_at: str
    retired_at: str | None


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _row_to_fact(row: sqlite3.Row) -> Fact:
    return Fact(
        uid=row["uid"], text=row["text"], kind=row["kind"],
        tags=json.loads(row["tags"]), source=row["source"],
        confidence=row["confidence"], supersedes=row["supersedes"],
        created_at=row["created_at"], updated_at=row["updated_at"],
        retired_at=row["retired_at"],
    )


class FactsRepo:
    """CRUD over the curated layer, keeping FTS and vector indexes in step.

    Index maintenance is explicit rather than trigger-driven because the
    vector index needs an embedding computed in Python; doing half in
    triggers and half in code would leave two places to get it wrong.
    """

    def __init__(self, conn: sqlite3.Connection, embedder) -> None:
        self.conn = conn
        self.embedder = embedder

    def _index(self, fact_id: int, text: str, tags: list[str]) -> None:
        self.conn.execute(
            "INSERT INTO facts_fts(rowid, text, tags) VALUES (?, ?, ?)",
            (fact_id, text, " ".join(tags)),
        )
        (vector,) = self.embedder.encode([text])
        self.conn.execute(
            "INSERT INTO facts_vec(fact_id, embedding) VALUES (?, ?)",
            (fact_id, sqlite_vec.serialize_float32(vector)),
        )

    def _deindex(self, fact_id: int) -> None:
        self.conn.execute("DELETE FROM facts_fts WHERE rowid = ?", (fact_id,))
        self.conn.execute("DELETE FROM facts_vec WHERE fact_id = ?", (fact_id,))

    def write(self, text: str, kind: str, tags: Sequence[str] = (),
              source: str = "human", supersedes: str | None = None) -> Fact:
        if kind not in KINDS:
            raise InvalidKind(kind)
        uid = secrets.token_urlsafe(8)
        now = _now()
        tag_list = list(tags)
        cur = self.conn.execute(
            "INSERT INTO facts(uid, text, kind, tags, source, supersedes, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (uid, text, kind, json.dumps(tag_list), source, supersedes, now, now),
        )
        self._index(cur.lastrowid, text, tag_list)
        return self.get(uid)

    def get(self, uid: str) -> Fact | None:
        row = self.conn.execute("SELECT * FROM facts WHERE uid = ?", (uid,)).fetchone()
        return _row_to_fact(row) if row else None

    def update(self, uid: str, text: str | None = None, kind: str | None = None,
               tags: Sequence[str] | None = None) -> Fact:
        row = self.conn.execute("SELECT * FROM facts WHERE uid = ?", (uid,)).fetchone()
        if row is None:
            raise FactNotFound(uid)

        if text is not None and text != row["text"]:
            # Material change: retire and supersede rather than mutate, so the
            # store never silently loses what it used to believe (spec 4.1).
            new_kind = kind or row["kind"]
            if new_kind not in KINDS:
                raise InvalidKind(new_kind)
            self.retire(uid)
            return self.write(
                text=text,
                kind=new_kind,
                tags=list(tags) if tags is not None else json.loads(row["tags"]),
                source=row["source"],
                supersedes=uid,
            )

        new_kind = kind or row["kind"]
        if new_kind not in KINDS:
            raise InvalidKind(new_kind)
        new_tags = list(tags) if tags is not None else json.loads(row["tags"])
        self.conn.execute(
            "UPDATE facts SET kind = ?, tags = ?, updated_at = ? WHERE uid = ?",
            (new_kind, json.dumps(new_tags), _now(), uid),
        )
        self._deindex(row["id"])
        self._index(row["id"], row["text"], new_tags)
        return self.get(uid)

    def retire(self, uid: str, reason: str | None = None) -> None:
        row = self.conn.execute("SELECT id FROM facts WHERE uid = ?", (uid,)).fetchone()
        if row is None:
            raise FactNotFound(uid)
        now = _now()
        self.conn.execute(
            "UPDATE facts SET retired_at = ?, updated_at = ? WHERE uid = ?",
            (now, now, uid),
        )
        self._deindex(row["id"])

    def recent(self, limit: int = 10, kind: str | None = None) -> list[Fact]:
        sql = "SELECT * FROM facts WHERE retired_at IS NULL"
        params: list = []
        if kind is not None:
            sql += " AND kind = ?"
            params.append(kind)
        sql += " ORDER BY updated_at DESC, id DESC LIMIT ?"
        params.append(limit)
        return [_row_to_fact(r) for r in self.conn.execute(sql, params)]
