from contextlib import contextmanager
from dataclasses import asdict

from fastmcp import FastMCP

from ai_mem.facts import FactsRepo
from ai_mem.profile_context import current_profile
from ai_mem.search import hybrid_search


def build_mcp(registry, embedder, settings) -> FastMCP:
    mcp = FastMCP("ai-mem")

    @contextmanager
    def _repo():
        conn = registry.connect(current_profile())
        try:
            yield conn, FactsRepo(conn, embedder)
        finally:
            conn.close()

    @mcp.tool
    def memory_search(query: str, limit: int = 8,
                      tags: list[str] | None = None) -> list[dict]:
        """Search long-term memory for durable facts about this user, their
        projects, preferences and past decisions.

        Call this at the start of a task, and whenever you are about to assume
        something about how the user works, what a project uses, or why a
        decision was made. Prefer searching over guessing.
        """
        with _repo() as (conn, _):
            return [asdict(h) for h in hybrid_search(
                conn, embedder, query, limit=limit, tags=tags,
                rrf_k=settings.rrf_k, max_distance=settings.max_distance)]

    @mcp.tool
    def memory_write(text: str, kind: str, tags: list[str] | None = None) -> dict:
        """Record one durable fact worth remembering in future sessions.

        `kind` is one of: user, preference, project, reference, decision.
        Write things that stay true beyond this conversation. Do not write
        transient task state, or anything the repository already records.
        """
        with _repo() as (_, repo):
            return asdict(repo.write(text, kind, tags or [], source="agent"))

    @mcp.tool
    def memory_update(uid: str, text: str | None = None, kind: str | None = None,
                      tags: list[str] | None = None) -> dict:
        """Amend an existing fact. Changing its text retires the old version
        and records the new one as superseding it, so history is preserved."""
        with _repo() as (_, repo):
            return asdict(repo.update(uid, text=text, kind=kind, tags=tags))

    @mcp.tool
    def memory_forget(uid: str, reason: str | None = None) -> dict:
        """Retire a fact that is no longer true. It stops appearing in
        searches but is never destroyed."""
        with _repo() as (_, repo):
            repo.retire(uid, reason)
            return {"uid": uid, "retired": True}

    @mcp.tool
    def memory_recent(limit: int = 10, kind: str | None = None) -> list[dict]:
        """List recently written or updated facts. Useful for reviewing what
        memory currently holds before adding something similar."""
        with _repo() as (_, repo):
            return [asdict(f) for f in repo.recent(limit=limit, kind=kind)]

    return mcp
