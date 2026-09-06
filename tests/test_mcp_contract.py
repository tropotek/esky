import pytest
from fastmcp import Client

from ai_mem.config import load_settings
from ai_mem.mcp_server import build_mcp
from ai_mem.profile_context import reset_profile, set_profile
from ai_mem.profiles import ProfileRegistry


@pytest.fixture
def mcp(tmp_path, embedder, monkeypatch):
    monkeypatch.setenv("AI_MEM_DATA_DIR", str(tmp_path))
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
            "text": "the ai-mem server listens on 8080",
            "kind": "project", "tags": ["infra"]})
        result = await client.call_tool("memory_search", {"query": "ai-mem port 8080"})
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
