from contextlib import contextmanager
from dataclasses import asdict

from fastmcp import FastMCP

from esky.facts import FactsRepo
from esky.profile_context import current_profile
from esky.search import hybrid_search


def build_mcp(registry, embedder, settings) -> FastMCP:
    mcp = FastMCP("esky")

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
    def memory_write(text: str, kind: str, tags: list[str] | None = None,
                     title: str | None = None) -> dict:
        """Record one durable fact worth remembering in future sessions.

        Write things that stay true beyond this conversation. Do not write
        transient task state, or anything the repository already records.

        `kind` is one of:
          user       - who the user is: role, expertise, context
          preference - how they want work done
          project    - goals, constraints, or state of ongoing work
          reference  - a pointer to something external: URL, ticket, dashboard
          research   - findings you gathered and concluded, with the conclusion
                       stated; use this rather than `reference` when the value
                       is the finding itself, not where it lives
          decision   - a choice made and the reasoning behind it

        `title` is an optional short label for scanning a list of facts; omit
        it when the text is already terse.

        `text` is stored and returned verbatim. Keep a short fact to one
        plain line. For anything longer, markdown is preferred and multi-line
        is fine: use a list for a set of items, a code fence for a command or
        a snippet, and headings only if the fact really has sections. Markup
        is structure, not decoration — it earns its place by making the fact
        easier to read back, so never bold a phrase for emphasis or wrap a
        one-line fact in a heading.
        """
        with _repo() as (_, repo):
            return asdict(
                repo.write(text, kind, tags or [], source="agent", title=title))

    @mcp.tool
    def memory_update(uid: str, text: str | None = None, kind: str | None = None,
                      tags: list[str] | None = None,
                      title: str | None = None) -> dict:
        """Amend an existing fact. Changing its text retires the old version
        and records the new one as superseding it, so history is preserved.
        Changing only the title, kind or tags amends it in place."""
        with _repo() as (_, repo):
            return asdict(
                repo.update(uid, text=text, kind=kind, tags=tags, title=title))

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
