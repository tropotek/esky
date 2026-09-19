import pytest

from esky.facts import FactsRepo
from esky.metrics import fact_stats, query_summary


@pytest.fixture
def repo(conn, embedder):
    return FactsRepo(conn, embedder)


def _log(conn, query, when, returned=0, matched=None, tags=(), top_uid=None):
    """Insert a query row at a chosen instant.

    The summaries are all about time, so the tests have to choose it; log_query
    stamps 'now' and would only ever exercise a single day.
    """
    import json
    conn.execute(
        "INSERT INTO queries(query, tags, returned_count, matched_count, "
        "top_uid, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (query, json.dumps(list(tags)), returned, matched, top_uid, when),
    )


NOW = "2026-09-19T12:00:00+00:00"


def test_the_window_is_the_last_n_days_inclusive(conn):
    summary = query_summary(conn, days=7, now=NOW)
    assert summary["days"] == 7
    assert summary["from"] == "2026-09-13"
    assert summary["to"] == "2026-09-19"


def test_searches_are_counted_within_the_window(conn):
    _log(conn, "inside", "2026-09-18T09:00:00+00:00")
    _log(conn, "also inside", "2026-09-19T09:00:00+00:00")

    assert query_summary(conn, days=7, now=NOW)["totals"]["searches"] == 2


def test_searches_before_the_window_are_left_out(conn):
    _log(conn, "ancient", "2026-01-01T09:00:00+00:00")

    assert query_summary(conn, days=7, now=NOW)["totals"]["searches"] == 0


def test_a_search_that_returned_nothing_counts_as_zero_match(conn):
    _log(conn, "unanswered", "2026-09-18T09:00:00+00:00", returned=0, matched=0)
    _log(conn, "answered", "2026-09-18T09:05:00+00:00", returned=3, matched=3)

    totals = query_summary(conn, days=7, now=NOW)["totals"]
    assert totals["zero_match"] == 1


def test_rows_without_a_matched_count_are_reported_as_unknown(conn):
    """Pre-v4 rows cannot supply it, and counting them as zero would invent
    evidence that memory failed."""
    _log(conn, "old row", "2026-09-18T09:00:00+00:00", returned=2, matched=None)

    assert query_summary(conn, days=7, now=NOW)["totals"]["unknown_matched"] == 1


def test_repeated_queries_count_once_as_distinct(conn):
    _log(conn, "same", "2026-09-17T09:00:00+00:00")
    _log(conn, "same", "2026-09-18T09:00:00+00:00")

    totals = query_summary(conn, days=7, now=NOW)["totals"]
    assert totals["searches"] == 2
    assert totals["distinct_queries"] == 1


def test_daily_counts_cover_every_day_including_the_silent_ones(conn):
    """A chart with days missing draws a false picture: a quiet day has to be
    a zero, not a gap."""
    _log(conn, "one", "2026-09-19T09:00:00+00:00")

    daily = query_summary(conn, days=3, now=NOW)["daily"]
    assert [d["date"] for d in daily] == ["2026-09-17", "2026-09-18", "2026-09-19"]
    assert [d["searches"] for d in daily] == [0, 0, 1]


def test_daily_counts_carry_the_zero_match_share(conn):
    _log(conn, "miss", "2026-09-19T09:00:00+00:00", returned=0)
    _log(conn, "hit", "2026-09-19T09:01:00+00:00", returned=4, matched=4)

    today = query_summary(conn, days=3, now=NOW)["daily"][-1]
    assert today == {"date": "2026-09-19", "searches": 2, "zero_match": 1}


def test_matched_counts_are_bucketed(conn):
    for matched in (0, 1, 2, 4, 9, 40):
        _log(conn, "q", "2026-09-19T09:00:00+00:00", returned=1, matched=matched)
    _log(conn, "q", "2026-09-19T09:00:00+00:00", returned=1, matched=None)

    buckets = {b["label"]: b["count"]
               for b in query_summary(conn, days=7, now=NOW)["match_buckets"]}
    assert buckets == {"0": 1, "1-2": 2, "3-5": 1, "6-10": 1, "11+": 1,
                       "unknown": 1}


def test_top_queries_are_ranked_with_their_misses(conn):
    for _ in range(3):
        _log(conn, "how do we deploy", "2026-09-18T09:00:00+00:00", returned=0)
    _log(conn, "docker", "2026-09-18T09:00:00+00:00", returned=2, matched=2)

    top = query_summary(conn, days=7, now=NOW)["top_queries"]
    assert top[0] == {"query": "how do we deploy", "count": 3, "zero_match": 3}
    assert top[1]["query"] == "docker"


def test_top_queries_are_capped(conn):
    for i in range(15):
        _log(conn, f"query {i}", "2026-09-18T09:00:00+00:00")

    assert len(query_summary(conn, days=7, now=NOW, top=10)["top_queries"]) == 10


def test_tag_filters_are_counted_one_row_at_a_time(conn):
    _log(conn, "a", "2026-09-18T09:00:00+00:00", tags=["infra", "docker"])
    _log(conn, "b", "2026-09-18T09:00:00+00:00", tags=["infra"])

    tags = {t["tag"]: t["count"]
            for t in query_summary(conn, days=7, now=NOW)["top_tags"]}
    assert tags == {"infra": 2, "docker": 1}


def test_the_facts_that_answer_most_often_are_named(conn, repo):
    fact = repo.write("the deployment uses docker compose", "project", [],
                      title="Deployment")
    for _ in range(2):
        _log(conn, "deploy", "2026-09-18T09:00:00+00:00", returned=1,
             matched=1, top_uid=fact.uid)

    (top,) = query_summary(conn, days=7, now=NOW)["top_facts"]
    assert top == {"uid": fact.uid, "count": 2, "title": "Deployment"}


def test_a_top_fact_that_has_since_been_deleted_still_reports(conn):
    """The uid outlives nothing here — facts are never hard-deleted — but a row
    logged against a profile restored from elsewhere can still miss."""
    _log(conn, "deploy", "2026-09-18T09:00:00+00:00", returned=1, top_uid="gone")

    (top,) = query_summary(conn, days=7, now=NOW)["top_facts"]
    assert top == {"uid": "gone", "count": 1, "title": None}


def test_an_empty_log_summarises_to_zeroes_not_an_error(conn):
    summary = query_summary(conn, days=7, now=NOW)
    assert summary["totals"]["searches"] == 0
    assert summary["top_queries"] == []
    assert len(summary["daily"]) == 7


def test_fact_stats_count_live_and_retired_separately(conn, repo):
    kept = repo.write("kept", "project", [])
    repo.write("dropped", "project", [])
    repo.retire(kept.uid)

    stats = fact_stats(conn, days=7, now=NOW)
    assert stats["facts"] == 1
    assert stats["retired"] == 1


def test_fact_stats_report_the_kind_mix_of_live_facts(conn, repo):
    repo.write("a", "project", [])
    repo.write("b", "project", [])
    repo.write("c", "preference", [])

    kinds = {k["kind"]: k["count"] for k in fact_stats(conn, days=7, now=NOW)["kinds"]}
    assert kinds == {"project": 2, "preference": 1}


def test_fact_stats_rank_tags_across_live_facts(conn, repo):
    repo.write("a", "project", ["infra", "docker"])
    repo.write("b", "project", ["infra"])

    tags = {t["tag"]: t["count"]
            for t in fact_stats(conn, days=7, now=NOW)["top_tags"]}
    assert tags == {"infra": 2, "docker": 1}


def test_fact_stats_chart_growth_by_day(conn, repo):
    fact = repo.write("a", "project", [])
    conn.execute("UPDATE facts SET created_at = ? WHERE uid = ?",
                 ("2026-09-18T09:00:00+00:00", fact.uid))

    daily = fact_stats(conn, days=3, now=NOW)["daily"]
    assert [d["date"] for d in daily] == ["2026-09-17", "2026-09-18", "2026-09-19"]
    assert [d["created"] for d in daily] == [0, 1, 0]


def test_fact_stats_chart_retirements_by_day(conn, repo):
    fact = repo.write("a", "project", [])
    repo.retire(fact.uid)
    conn.execute("UPDATE facts SET retired_at = ? WHERE uid = ?",
                 ("2026-09-18T09:00:00+00:00", fact.uid))

    daily = fact_stats(conn, days=3, now=NOW)["daily"]
    assert [d["retired"] for d in daily] == [0, 1, 0]


def test_fact_stats_name_the_span_the_store_covers(conn, repo):
    fact = repo.write("a", "project", [])
    conn.execute("UPDATE facts SET created_at = ? WHERE uid = ?",
                 ("2025-01-01T09:00:00+00:00", fact.uid))
    repo.write("b", "project", [])

    stats = fact_stats(conn, days=7, now=NOW)
    assert stats["oldest"].startswith("2025-01-01")
    assert stats["newest"] > stats["oldest"]


def test_fact_stats_on_an_empty_store_report_no_span(conn):
    stats = fact_stats(conn, days=7, now=NOW)
    assert stats["facts"] == 0
    assert stats["oldest"] is None
    assert stats["newest"] is None
