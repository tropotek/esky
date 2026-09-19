import pytest
from fastmcp import Client

from esky.config import load_settings
from esky.mcp_server import build_mcp
from esky.profile_context import reset_profile, set_profile
from esky.profiles import ProfileRegistry


@pytest.fixture
def mcp(tmp_path, embedder, monkeypatch):
    monkeypatch.setenv("ESKY_DATA_DIR", str(tmp_path))
    registry = ProfileRegistry(tmp_path)
    registry.create("work")
    registry.create("personal")
    return build_mcp(registry, embedder, load_settings())


@pytest.fixture
def as_work():
    token = set_profile("work")
    yield
    reset_profile(token)


async def test_exposes_exactly_five_tools(mcp):
    async with Client(mcp) as client:
        names = {t.name for t in await client.list_tools()}
    assert names == {"memory_search", "memory_write", "memory_update",
                     "memory_forget", "memory_recent"}


async def test_write_then_search_roundtrip(mcp, as_work):
    async with Client(mcp) as client:
        await client.call_tool("memory_write", {
            "text": "the esky server listens on 8080",
            "kind": "project", "tags": ["infra"]})
        result = await client.call_tool("memory_search", {"query": "esky port 8080"})
    assert "8080" in str(result.content)


async def test_profiles_are_isolated(mcp):
    token = set_profile("work")
    async with Client(mcp) as client:
        await client.call_tool("memory_write", {
            "text": "quarterly revenue target is confidential",
            "kind": "project", "tags": []})
    reset_profile(token)

    token = set_profile("personal")
    async with Client(mcp) as client:
        result = await client.call_tool("memory_search", {"query": "quarterly revenue"})
    reset_profile(token)
    assert "revenue" not in str(result.content)


async def test_write_rejects_bad_kind(mcp, as_work):
    async with Client(mcp) as client:
        result = await client.call_tool(
            "memory_write", {"text": "x", "kind": "bogus", "tags": []},
            raise_on_error=False)
    assert result.is_error


async def test_forget_removes_from_search(mcp, as_work):
    async with Client(mcp) as client:
        written = await client.call_tool("memory_write", {
            "text": "a transient note about nothing", "kind": "project", "tags": []})
        uid = written.data["uid"]
        await client.call_tool("memory_forget", {"uid": uid})
        result = await client.call_tool("memory_search", {"query": "transient note"})
    assert "transient" not in str(result.content)


async def test_recent_lists_written_facts(mcp, as_work):
    async with Client(mcp) as client:
        await client.call_tool("memory_write", {
            "text": "uses docker for everything", "kind": "preference", "tags": []})
        result = await client.call_tool("memory_recent", {})
    assert "docker" in str(result.content)


async def test_write_accepts_a_title(mcp, as_work):
    async with Client(mcp) as client:
        written = await client.call_tool("memory_write", {
            "text": "the esky server listens on 8080", "kind": "project",
            "tags": [], "title": "server port"})
    assert written.data["title"] == "server port"


async def test_search_is_logged(mcp, as_work, tmp_path):
    from esky.querylog import recent_queries

    async with Client(mcp) as client:
        await client.call_tool("memory_write", {
            "text": "the esky server listens on 8080", "kind": "project",
            "tags": ["infra"]})
        await client.call_tool("memory_search", {"query": "which port"})

    conn = ProfileRegistry(tmp_path).connect("work")
    try:
        entries = recent_queries(conn)
    finally:
        conn.close()
    assert [e.query for e in entries] == ["which port"]


async def test_a_search_finding_nothing_is_logged(mcp, as_work, tmp_path):
    from esky.querylog import recent_queries

    async with Client(mcp) as client:
        await client.call_tool("memory_search", {"query": "zzzznonexistenttoken"})

    conn = ProfileRegistry(tmp_path).connect("work")
    try:
        (entry,) = recent_queries(conn)
    finally:
        conn.close()
    assert entry.returned_count == 0
    assert entry.matched_count == 0


async def test_forget_echoes_the_reason_it_recorded(mcp, as_work):
    """The reason is stored but no read surface exposes retired facts, so the
    call that recorded it is the only place it can be confirmed."""
    async with Client(mcp) as client:
        written = await client.call_tool("memory_write", {
            "text": "the server lives at 192.168.1.5", "kind": "project",
            "tags": []})
        result = await client.call_tool("memory_forget", {
            "uid": written.data["uid"], "reason": "host was reassigned"})
    assert result.data["reason"] == "host was reassigned"
