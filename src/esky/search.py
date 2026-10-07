import json
import re
import sqlite3
from dataclasses import dataclass

import sqlite_vec

_FTS_SAFE = re.compile(r"[^\w\s]")

# A ticket key (`sc-3469`) or a bare issue/PR number (`#123`). Neither means
# anything to the embedder, and FTS5 splits the first into `sc` OR `3469`, so a
# lookup by ID has to be a literal match.
_ID = re.compile(r"(?<![\w-])(?:[A-Za-z][A-Za-z0-9]*-\d+|#\d+)(?!\w)")
_UID = re.compile(r"^[A-Za-z0-9_-]{11}$")

# Above any RRF score (bounded by 2 / (rrf_k + 1)), so exact matches sort first.
_EXACT_BASE = 1.0


@dataclass(frozen=True)
class SearchHit:
    uid: str
    title: str | None
    text: str
    kind: str
    tags: list[str]
    updated_at: str
    layer: str
    score: float


@dataclass(frozen=True)
class SearchResult:
    hits: list[SearchHit]
    matched: int
    exact_count: int
    top_distance: float | None


def _sanitise(query: str) -> str:
    """FTS5 MATCH treats punctuation and bare AND/OR as syntax; strip it and
    OR the remaining tokens so a natural-language query cannot be a syntax
    error."""
    tokens = _FTS_SAFE.sub(" ", query).split()
    return " OR ".join(f'"{t}"' for t in tokens)


def _tag_clause(tags: list[str] | None, alias: str) -> tuple[str, list[str]]:
    """A tag restriction for a ranking query, so tags narrow what the pool is
    drawn from rather than what survives it."""
    if not tags:
        return "", []
    placeholders = ",".join("?" * len(tags))
    return (f" AND EXISTS (SELECT 1 FROM json_each({alias}.tags) "
            f"WHERE json_each.value IN ({placeholders}))"), list(tags)


def _lexical_ranking(conn: sqlite3.Connection, query: str, pool: int,
                     tags: list[str] | None = None) -> list[int]:
    match = _sanitise(query)
    if not match:
        return []
    clause, tag_params = _tag_clause(tags, "f")
    rows = conn.execute(
        "SELECT f.id FROM facts_fts JOIN facts f ON f.id = facts_fts.rowid "
        "WHERE facts_fts MATCH ? AND f.retired_at IS NULL " + clause +
        " ORDER BY bm25(facts_fts) LIMIT ?",
        (match, *tag_params, pool),
    ).fetchall()
    return [r[0] for r in rows]


def _vector_ranking(conn, embedder, query: str, pool: int,
                    max_distance: float, tags: list[str] | None = None) -> list[int]:
    return [fact_id for fact_id, _ in
            _vector_neighbours(conn, embedder, query, pool, max_distance, tags)]


def _vector_neighbours(conn, embedder, query: str, pool: int,
                       max_distance: float, tags: list[str] | None = None
                       ) -> list[tuple[int, float]]:
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

    Deployed traffic runs higher than this corpus suggests: top hits observed
    between 0.62 and 0.88, most of them above 0.75, on searches whose results
    were good. Short keyword queries are less similar to a stored sentence
    than a seeded phrase is, so lowering the floor towards 0.75 would discard
    most real hits. Check the query log before moving it.
    """
    (vector,) = embedder.encode([query])
    clause, tag_params = _tag_clause(tags, "f")
    rows = conn.execute(
        "SELECT v.fact_id, v.distance FROM facts_vec v JOIN facts f ON f.id = v.fact_id "
        "WHERE v.embedding MATCH ? AND k = ? AND f.retired_at IS NULL "
        "AND v.distance <= ? " + clause + " ORDER BY v.distance",
        (sqlite_vec.serialize_float32(vector), pool, max_distance, *tag_params),
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


def _exact_ranking(conn, query: str, tags: list[str] | None = None
                   ) -> dict[int, int]:
    """Facts that contain an ID from the query literally, mapped to how many
    of the query's IDs they contain.

    FTS5 narrows the candidates by phrase, then a word-boundary check on the
    real text decides: FTS drops `#`, and `#12` must not match `#123`. A bare
    11-character token is also tried as a fact uid, since nothing else can
    fetch one.
    """
    found: dict[int, int] = {}
    clause, tag_params = _tag_clause(tags, "f")
    ids = {m.group(0).lower() for m in _ID.finditer(query)}
    for ident in ids:
        phrase = '"' + " ".join(re.findall(r"\w+", ident)) + '"'
        literal = re.compile(r"(?<![\w-])" + re.escape(ident) + r"(?!\w)")
        rows = conn.execute(
            "SELECT f.id, coalesce(f.title, '') || ' ' || f.text || ' ' || f.tags "
            "FROM facts_fts JOIN facts f ON f.id = facts_fts.rowid "
            "WHERE facts_fts MATCH ? AND f.retired_at IS NULL " + clause,
            (phrase, *tag_params),
        ).fetchall()
        for fact_id, haystack in rows:
            if literal.search(haystack.lower()):
                found[fact_id] = found.get(fact_id, 0) + 1
    uids = [t for t in query.split() if _UID.match(t)]
    if uids:
        marks = ",".join("?" * len(uids))
        for (fact_id,) in conn.execute(
                f"SELECT f.id FROM facts f WHERE f.uid IN ({marks}) "
                "AND f.retired_at IS NULL " + clause, (*uids, *tag_params)):
            found[fact_id] = found.get(fact_id, 0) + 1
    return found


def hybrid_search(conn, embedder, query: str, limit: int = 8,
                  tags: list[str] | None = None, rrf_k: int = 60,
                  facts_weight: float = 1.0,
                  max_distance: float = 0.9) -> list[SearchHit]:
    """The hits alone, for callers that do not care how many were cut off."""
    return hybrid_search_with_stats(
        conn, embedder, query, limit=limit, tags=tags, rrf_k=rrf_k,
        facts_weight=facts_weight, max_distance=max_distance)[0]


def hybrid_search_with_stats(conn, embedder, query: str, limit: int = 8,
                             tags: list[str] | None = None, rrf_k: int = 60,
                             facts_weight: float = 1.0,
                             max_distance: float = 0.9
                             ) -> tuple[list[SearchHit], int]:
    """The hits and how many were matched before `limit` was applied."""
    result = hybrid_search_detailed(
        conn, embedder, query, limit=limit, tags=tags, rrf_k=rrf_k,
        facts_weight=facts_weight, max_distance=max_distance)
    return result.hits, result.matched


def hybrid_search_detailed(conn, embedder, query: str, limit: int = 8,
                           tags: list[str] | None = None, rrf_k: int = 60,
                           facts_weight: float = 1.0,
                           max_distance: float = 0.9) -> SearchResult:
    """Fuse a BM25 ranking and a vector KNN ranking by reciprocal rank fusion,
    with literal ID matches ranked ahead of the fusion.

    `matched` is how many facts were found before `limit` was applied. It is
    what tells "memory knew nothing" apart from "memory knew plenty and you
    asked for two" — see querylog. `exact_count` is how many of those were
    literal ID matches, and `top_distance` is the vector distance of the best
    hit (None when it came from the lexical side only): together they tell a
    real hit from a weak nearest neighbour.

    RRF is used rather than score normalisation because BM25 scores and cosine
    distances are not on comparable scales, and rank fusion needs no per-corpus
    tuning (spec 5). `facts_weight` scales the one layer there is, so it
    changes nothing; it is kept because removing it costs a signature change
    and buys nothing.
    """
    pool = max(limit * 5, 20)
    scores: dict[int, float] = {}
    neighbours = _vector_neighbours(conn, embedder, query, pool, max_distance,
                                    tags)
    distances = dict(neighbours)
    for ranking in (_lexical_ranking(conn, query, pool, tags),
                    [fact_id for fact_id, _ in neighbours]):
        for rank, fact_id in enumerate(ranking, start=1):
            scores[fact_id] = scores.get(fact_id, 0.0) + facts_weight / (rrf_k + rank)
    exact = _exact_ranking(conn, query, tags)
    for fact_id, count in exact.items():
        scores[fact_id] = scores.get(fact_id, 0.0) + _EXACT_BASE + count

    if not scores:
        return SearchResult([], 0, 0, None)

    placeholders = ",".join("?" * len(scores))
    sql = (f"SELECT * FROM facts WHERE id IN ({placeholders}) "
           "AND retired_at IS NULL")
    params: list = list(scores)

    rows = conn.execute(sql, params).fetchall()
    hits = [
        SearchHit(uid=r["uid"], title=r["title"], text=r["text"], kind=r["kind"],
                  tags=json.loads(r["tags"]), updated_at=r["updated_at"],
                  layer="facts", score=scores[r["id"]])
        for r in rows
    ]
    by_uid = {r["uid"]: r["id"] for r in rows}
    hits.sort(key=lambda h: h.score, reverse=True)
    top = hits[:limit]
    top_distance = distances.get(by_uid[top[0].uid]) if top else None
    return SearchResult(top, len(hits), len(exact), top_distance)
