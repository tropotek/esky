import pytest
from starlette.testclient import TestClient

from esky.app import build_app
from esky.auth import issue_token
from esky.config import load_settings
from esky.profiles import ProfileRegistry


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ESKY_DATA_DIR", str(tmp_path))
    registry = ProfileRegistry(tmp_path)
    registry.create("work")
    conn = registry.connect("work")
    token = issue_token(conn)
    conn.close()
    with TestClient(build_app(load_settings())) as c:
        c.headers.update({"Authorization": f"Bearer {token}"})
        yield c


def test_health_is_open(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_profiles_lists_known(client):
    assert client.get("/api/profiles").json() == {"profiles": ["work"]}


def test_stats_for_known_profile(client):
    body = client.get("/api/work/stats").json()
    assert body["profile"] == "work"
    assert body["facts"] == 0


def test_stats_for_unknown_profile_is_401(client):
    assert client.get("/api/nope/stats").status_code == 401


def test_unknown_mcp_profile_is_401(client):
    # A distinct 404 would leak which profiles exist.
    assert client.post("/mcp/nope").status_code == 401


def test_unknown_profile_creates_no_file(client, tmp_path):
    client.post("/mcp/typo")
    assert [p.name for p in tmp_path.glob("*.db")] == ["work.db"]


def test_traversal_attempt_is_a_route_miss_not_a_500(client):
    # A name containing a slash matches no route, so Starlette answers 404
    # before our handler runs. That is a routing fact, identical for any
    # malformed URL, so it reveals nothing about which profiles exist —
    # unlike a well-formed unknown profile, which must 401 (below).
    assert client.get("/api/..%2Fetc/stats").status_code == 404


def test_mcp_endpoint_is_reachable_for_known_profile(client):
    # No MCP session headers, so the MCP app rejects it — but with a protocol
    # error, which proves routing reached the MCP app rather than 404ing.
    assert client.post("/mcp/work").status_code != 404


def test_stats_reports_the_kind_mix(client):
    body = client.get("/api/work/stats").json()
    assert body["kinds"] == []
    assert body["daily"] != []


def test_stats_rejects_a_nonsense_window(client):
    assert client.get("/api/work/stats?days=0").status_code == 400


def test_queries_summary_for_known_profile(client):
    body = client.get("/api/work/queries/summary?days=7").json()
    assert body["profile"] == "work"
    assert body["days"] == 7
    assert body["totals"]["searches"] == 0
    assert len(body["daily"]) == 7


def test_queries_summary_defaults_to_thirty_days(client):
    assert client.get("/api/work/queries/summary").json()["days"] == 30


def test_queries_summary_window_is_capped(client):
    assert client.get("/api/work/queries/summary?days=9999").json()["days"] == 365


def test_queries_summary_rejects_a_nonsense_window(client):
    assert client.get("/api/work/queries/summary?days=nope").status_code == 400


def test_queries_summary_for_unknown_profile_is_401(client):
    assert client.get("/api/nope/queries/summary").status_code == 401


def _seed(client, texts):
    """Write a batch of facts over MCP so the facts endpoint has something to
    page through. Writing them one at a time via the repo would need a second
    database connection to the same file."""
    from esky.auth import issue_token
    from esky.facts import FactsRepo
    from esky.profiles import ProfileRegistry
    from pathlib import Path
    import os
    registry = ProfileRegistry(Path(os.environ["ESKY_DATA_DIR"]))
    conn = registry.connect("work")
    try:
        from esky.embedding import Embedder
        from esky.config import load_settings
        repo = FactsRepo(conn, Embedder(load_settings().embed_model))
        return [repo.write(t, "project", []) for t in texts]
    finally:
        conn.close()


def test_facts_lists_live_memories_with_a_total_and_zero_offset(client):
    _seed(client, ["one", "two", "three"])
    body = client.get("/api/work/facts?limit=10").json()
    assert body["profile"] == "work"
    assert body["total"] == 3
    assert body["limit"] == 10
    assert body["offset"] == 0
    assert [f["text"] for f in body["facts"]] == ["three", "two", "one"]


def test_facts_pages_with_offset(client):
    _seed(client, ["one", "two", "three", "four"])
    body = client.get("/api/work/facts?limit=2&offset=2").json()
    assert body["total"] == 4
    assert [f["text"] for f in body["facts"]] == ["two", "one"]


def test_facts_search_returns_matches_with_total_matched(client):
    """A search's total is `matched` from the hybrid searcher: how many hit
    before the page's limit was applied, so the pager knows where the end is."""
    _seed(client, ["docker runs the container",
                   "redis caches the lookup",
                   "docker compose brings it up"])
    body = client.get("/api/work/facts?q=docker&limit=10").json()
    assert body["q"] == "docker"
    assert body["total"] >= 2
    assert all("docker" in f["text"] for f in body["facts"][:2])


def test_facts_defaults_to_fifty_per_page(client):
    assert client.get("/api/work/facts").json()["limit"] == 50


def test_facts_limit_is_capped(client):
    assert client.get("/api/work/facts?limit=9999").json()["limit"] == 200


def test_facts_rejects_a_negative_offset(client):
    assert client.get("/api/work/facts?offset=-1").status_code == 400


def test_facts_rejects_a_zero_limit(client):
    assert client.get("/api/work/facts?limit=0").status_code == 400


def test_facts_for_unknown_profile_is_401(client):
    assert client.get("/api/nope/facts").status_code == 401


def test_facts_without_a_token_is_401(client):
    client.headers.pop("Authorization", None)
    assert client.get("/api/work/facts").status_code == 401
