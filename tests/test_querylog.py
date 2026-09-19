import pytest

from esky.facts import FactsRepo
from esky.querylog import log_query, recent_queries
from esky.search import hybrid_search, hybrid_search_with_stats


@pytest.fixture
def repo(conn, embedder):
    return FactsRepo(conn, embedder)


def test_a_search_is_recorded_with_its_hit_count(conn, embedder, repo):
    repo.write("the deployment uses docker compose", "project", ["infra"])
    hits = hybrid_search(conn, embedder, "docker compose")
    log_query(conn, "docker compose", hits)

    (entry,) = recent_queries(conn)
    assert entry.query == "docker compose"
    assert entry.returned_count == len(hits)
    assert entry.created_at


def test_a_search_that_found_nothing_is_still_recorded(conn, embedder):
    """The whole point of the log: a query memory could not answer is the
    signal for what belongs in it."""
    log_query(conn, "how do we deploy", hybrid_search(conn, embedder, "how do we deploy"))

    (entry,) = recent_queries(conn)
    assert entry.returned_count == 0
    assert entry.top_uid is None


def test_the_best_hit_is_recorded(conn, embedder, repo):
    written = repo.write("the deployment uses docker compose", "project", [])
    hits = hybrid_search(conn, embedder, "docker compose")
    log_query(conn, "docker compose", hits)

    assert recent_queries(conn)[0].top_uid == written.uid


def test_tags_are_recorded_when_a_search_was_filtered(conn, embedder, repo):
    repo.write("prefers tabs over spaces", "preference", ["style"])
    hits = hybrid_search(conn, embedder, "tabs", tags=["style"])
    log_query(conn, "tabs", hits, tags=["style"])

    assert recent_queries(conn)[0].tags == ["style"]


def test_queries_come_back_newest_first(conn, embedder):
    for q in ("first query", "second query", "third query"):
        log_query(conn, q, [])

    assert [e.query for e in recent_queries(conn)] == [
        "third query", "second query", "first query"]


def test_the_limit_is_respected(conn):
    for i in range(5):
        log_query(conn, f"query {i}", [])

    assert len(recent_queries(conn, limit=2)) == 2


def test_matched_count_records_what_the_limit_cut_off(conn, embedder, repo):
    """The returned count is bounded by `limit`; the matched count is not. Both
    are needed to tell 'memory knew nothing' from 'memory knew plenty'."""
    for i in range(5):
        repo.write(f"alpha record {i}", "project", [])
    hits, matched = hybrid_search_with_stats(conn, embedder, "alpha", limit=2)
    log_query(conn, "alpha", hits, matched=matched)

    entry = recent_queries(conn)[0]
    assert entry.returned_count == 2
    assert entry.matched_count == 5


def test_matched_count_is_unknown_when_not_supplied(conn):
    log_query(conn, "a query", [])
    assert recent_queries(conn)[0].matched_count is None
