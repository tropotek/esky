import pytest
from starlette.testclient import TestClient

from ai_mem.app import build_app
from ai_mem.auth import issue_token
from ai_mem.config import load_settings
from ai_mem.profiles import ProfileRegistry


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_MEM_DATA_DIR", str(tmp_path))
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
    assert client.post("/mcp/work", headers=auth("aimem_nonsense")).status_code == 401


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
    wrong = client.post("/mcp/work", headers=auth("aimem_wrong"))
    assert missing.status_code == wrong.status_code
    assert missing.json() == wrong.json()


def test_unknown_profile_still_creates_no_file(setup, tmp_path):
    client, work_token, _ = setup
    client.post("/mcp/typo", headers=auth(work_token))
    assert sorted(p.stem for p in tmp_path.glob("*.db")) == [
        "personal", "untokened", "work"]
