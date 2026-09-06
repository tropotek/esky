import pytest
from starlette.testclient import TestClient

from ai_mem.app import build_app
from ai_mem.config import load_settings
from ai_mem.profiles import ProfileRegistry


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_MEM_DATA_DIR", str(tmp_path))
    ProfileRegistry(tmp_path).create("work")
    with TestClient(build_app(load_settings())) as c:
        yield c


def test_health_is_open(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_profiles_lists_known(client):
    assert client.get("/api/profiles").json() == {"profiles": ["work"]}


def test_stats_for_known_profile(client):
    body = client.get("/api/work/stats").json()
    assert body["profile"] == "work"
    assert body["facts"] == 0


def test_stats_for_unknown_profile_is_404(client):
    assert client.get("/api/nope/stats").status_code == 404


def test_unknown_mcp_profile_is_404(client):
    assert client.post("/mcp/nope").status_code == 404


def test_unknown_profile_creates_no_file(client, tmp_path):
    client.post("/mcp/typo")
    assert [p.name for p in tmp_path.glob("*.db")] == ["work.db"]


def test_invalid_profile_name_is_404_not_500(client):
    assert client.get("/api/..%2Fetc/stats").status_code == 404


def test_mcp_endpoint_is_reachable_for_known_profile(client):
    # No MCP session headers, so the MCP app rejects it — but with a protocol
    # error, which proves routing reached the MCP app rather than 404ing.
    assert client.post("/mcp/work").status_code != 404
