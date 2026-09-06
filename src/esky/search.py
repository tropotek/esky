import json
import re
import sqlite3
from dataclasses import dataclass

import sqlite_vec

_FTS_SAFE = re.compile(r"[^\w\s]")


@dataclass(frozen=True)
class SearchHit:
    uid: str
    text: str
    kind: str
    tags: list[str]
    layer: str
    score: float


def _sanitise(query: str) -> str:
    """FTS5 MATCH treats punctuation and bare AND/OR as syntax; strip it and
    OR the remaining tokens so a natural-language query cannot be a syntax
    error."""
    tokens = _FTS_SAFE.sub(" ", query).split()
    return " OR ".join(f'"{t}"' for t in tokens)


def _lexical_ranking(conn: sqlite3.Connection, query: str, pool: int) -> list[int]:
    match = _sanitise(query)
    if not match:
        return []
    rows = conn.execute(
        "SELECT f.id FROM facts_fts JOIN facts f ON f.id = facts_fts.rowid "
        "WHERE facts_fts MATCH ? AND f.retired_at IS NULL "
        "ORDER BY bm25(facts_fts) LIMIT ?",
        (match, pool),
    ).fetchall()
    return [r[0] for r in rows]


def _vector_ranking(conn, embedder, query: str, pool: int,
                    max_distance: float) -> list[int]:
    """Nearest neighbours within a relevance floor.

    KNN always returns k results however unrelated they are, so without a
    cutoff a nonsense query still hands the caller confident-looking facts.

    Measured L2 distances over unit-normalised bge-small vectors on a small
    seeded corpus:
        related   'docker compose'          -> 0.541
        related   'how do we deploy'        -> 0.736
        unrelated 'zzzznonexistenttoken'    -> 0.875
        unrelated 'recipe for banana bread' -> 1.001
    The bands separate, but not by much. 0.9 sits in the gap; tune via
    ESKY_MAX_DISTANCE and re-measure if recall looks wrong.
    """
    (vector,) = embedder.encode([query])
    rows = conn.execute(
        "SELECT v.fact_id FROM facts_vec v JOIN facts f ON f.id = v.fact_id "
        "WHERE v.embedding MATCH ? AND k = ? AND f.retired_at IS NULL "
        "AND v.distance <= ? ORDER BY v.distance",
        (sqlite_vec.serialize_float32(vector), pool, max_distance),
    ).fetchall()
    return [r[0] for r in rows]


def hybrid_search(conn, embedder, query: str, limit: int = 8,
                  tags: list[str] | None = None, rrf_k: int = 60,
                  facts_weight: float = 1.0,
                  max_distance: float = 0.9) -> list[SearchHit]:
    """Fuse a BM25 ranking and a vector KNN ranking by reciprocal rank fusion.

    RRF is used rather than score normalisation because BM25 scores and cosine
    distances are not on comparable scales, and rank fusion needs no per-corpus
    tuning (spec 5). `facts_weight` exists so Phase 2 can add the observations
    layer without changing this signature.
    """
    pool = max(limit * 5, 20)
    scores: dict[int, float] = {}
    for ranking in (_lexical_ranking(conn, query, pool),
                    _vector_ranking(conn, embedder, query, pool, max_distance)):
        for rank, fact_id in enumerate(ranking, start=1):
            scores[fact_id] = scores.get(fact_id, 0.0) + facts_weight / (rrf_k + rank)

    if not scores:
        return []

    placeholders = ",".join("?" * len(scores))
    sql = (f"SELECT * FROM facts WHERE id IN ({placeholders}) "
           "AND retired_at IS NULL")
    params: list = list(scores)
    if tags:
        sql += (" AND EXISTS (SELECT 1 FROM json_each(facts.tags) "
                "WHERE json_each.value IN (" + ",".join("?" * len(tags)) + "))")
        params += tags

    hits = [
        SearchHit(uid=r["uid"], text=r["text"], kind=r["kind"],
                  tags=json.loads(r["tags"]), layer="facts", score=scores[r["id"]])
        for r in conn.execute(sql, params)
    ]
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:limit]
