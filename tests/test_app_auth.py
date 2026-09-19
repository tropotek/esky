import pytest
from starlette.testclient import TestClient

from esky.app import build_app
from esky.auth import issue_token
from esky.config import load_settings
from esky.profiles import ProfileRegistry


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("ESKY_DATA_DIR", str(tmp_path))
    registry = ProfileRegistry(tmp_path)
    registry.create("work")
    registry.create("personal")
    registry.create("untokened")

    conn = registry.connect("work")
    work_token = issue_token(conn)
    conn.close()

    conn = registry.connect("personal")
    personal_token = issue_token(conn)
    conn.close()

    with TestClient(build_app(load_settings())) as client:
        yield client, work_token, personal_token


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_valid_token_reaches_the_mcp_app(setup):
    client, work_token, _ = setup
    assert client.post("/mcp/work", headers=auth(work_token)).status_code != 401


def test_missing_token_is_rejected(setup):
    client, _, _ = setup
    assert client.post("/mcp/work").status_code == 401


def test_another_profiles_token_is_rejected(setup):
    client, _, personal_token = setup
    assert client.post("/mcp/work", headers=auth(personal_token)).status_code == 401


def test_garbage_token_is_rejected(setup):
    client, _, _ = setup
    assert client.post("/mcp/work", headers=auth("esky_nonsense")).status_code == 401


def test_profile_without_an_issued_token_fails_closed(setup):
    client, work_token, _ = setup
    assert client.post("/mcp/untokened").status_code == 401
    assert client.post("/mcp/untokened", headers=auth(work_token)).status_code == 401


def test_unknown_profile_is_401_not_404(setup):
    """A 404 here would let anyone on the LAN enumerate profile names."""
    client, work_token, _ = setup
    assert client.post("/mcp/nosuchprofile").status_code == 401
    assert client.post("/mcp/nosuchprofile", headers=auth(work_token)).status_code == 401


def test_unknown_and_unauthorised_are_indistinguishable(setup):
    client, _, _ = setup
    missing = client.post("/mcp/nosuchprofile")
    wrong = client.post("/mcp/work", headers=auth("esky_wrong"))
    assert missing.status_code == wrong.status_code
    assert missing.json() == wrong.json()


def test_unknown_profile_still_creates_no_file(setup, tmp_path):
    client, work_token, _ = setup
    client.post("/mcp/typo", headers=auth(work_token))
    assert sorted(p.stem for p in tmp_path.glob("*.db")) == [
        "personal", "untokened", "work"]


def test_health_needs_no_token(setup):
    client, _, _ = setup
    assert client.get("/health").json() == {"status": "ok"}


def test_profiles_without_a_token_is_rejected(setup):
    client, _, _ = setup
    assert client.get("/api/profiles").status_code == 401


def test_profiles_returns_only_the_granted_profile(setup):
    client, work_token, _ = setup
    body = client.get("/api/profiles", headers=auth(work_token)).json()
    assert body == {"profiles": ["work"]}


def test_stats_requires_the_matching_token(setup):
    client, work_token, personal_token = setup
    assert client.get("/api/work/stats", headers=auth(work_token)).status_code == 200
    assert client.get("/api/work/stats", headers=auth(personal_token)).status_code == 401
    assert client.get("/api/work/stats").status_code == 401


def test_stats_for_unknown_profile_is_401(setup):
    client, work_token, _ = setup
    assert client.get("/api/nope/stats", headers=auth(work_token)).status_code == 401


def test_traversal_attempt_is_a_route_miss_not_a_500(setup):
    client, work_token, _ = setup
    resp = client.get("/api/..%2Fetc/stats", headers=auth(work_token))
    assert resp.status_code == 404


def test_wellformed_unknown_profile_is_indistinguishable_from_unauthorised(setup):
    """The property that actually matters: no profile-name oracle."""
    client, work_token, _ = setup
    unknown = client.get("/api/nosuchprofile/stats", headers=auth(work_token))
    unauthorised = client.get("/api/personal/stats", headers=auth(work_token))
    assert unknown.status_code == unauthorised.status_code == 401
    assert unknown.json() == unauthorised.json()


def test_queries_endpoint_returns_the_log(setup):
    client, work_token, _ = setup
    r = client.get("/api/work/queries", headers=auth(work_token))
    assert r.status_code == 200
    assert r.json() == {"profile": "work", "queries": []}


def test_queries_endpoint_rejects_another_profiles_token(setup):
    client, _, personal_token = setup
    assert client.get(
        "/api/work/queries", headers=auth(personal_token)).status_code == 401


def test_queries_endpoint_rejects_a_missing_token(setup):
    client, _, _ = setup
    assert client.get("/api/work/queries").status_code == 401


def test_queries_limit_rejects_a_negative_value(setup):
    """SQLite reads LIMIT -1 as 'no limit', so an unvalidated negative silently
    dumps the whole log past the cap."""
    client, work_token, _ = setup
    r = client.get("/api/work/queries?limit=-1", headers=auth(work_token))
    assert r.status_code == 400


def test_queries_limit_rejects_a_non_number(setup):
    client, work_token, _ = setup
    r = client.get("/api/work/queries?limit=abc", headers=auth(work_token))
    assert r.status_code == 400
