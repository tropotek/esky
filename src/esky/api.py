from dataclasses import asdict

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from esky.auth import UNAUTHORIZED_BODY, authorize
from esky.facts import FactsRepo
from esky.metrics import fact_stats, query_summary
from esky.querylog import recent_queries
from esky.search import hybrid_search_with_stats

# The deepest page a search may address. Matches the posture elsewhere in the
# codebase: the store is small, so paging past this is almost certainly a
# crafted URL rather than real traffic, and expanding the pool further would
# only make the search slower for everyone.
_SEARCH_PAGING_CAP = 500


def _positive_int(value, maximum: int) -> int:
    """Parse a caller-supplied count, refusing anything SQLite would misread.

    A negative LIMIT means 'no limit' in SQLite, so an unchecked value is not
    merely odd — it silently defeats the cap it was supposed to be bounded by.
    """
    number = int(value)
    if number < 1:
        raise ValueError(number)
    return min(number, maximum)


def _non_negative_int(value, maximum: int) -> int:
    """Parse an offset. Zero is the first page; negative means SQLite ignores it."""
    number = int(value)
    if number < 0:
        raise ValueError(number)
    return min(number, maximum)


def build_api(registry, embedder=None) -> Starlette:
    def unauthorized():
        return JSONResponse(UNAUTHORIZED_BODY, status_code=401)

    async def health(request):
        """Unauthenticated on purpose: the compose healthcheck needs it and it
        reveals nothing about what the server holds."""
        return JSONResponse({"status": "ok"})

    async def profiles(request):
        """Report which profile the presented token grants.

        Scanning every profile is O(n) with n in single digits, and it gives
        an operator a way to confirm a token works without guessing its URL.
        """
        header = request.headers.get("authorization")
        granted = [name for name in registry.list()
                   if authorize(registry, name, header)]
        if not granted:
            return unauthorized()
        return JSONResponse({"profiles": granted})

    async def stats(request):
        """What the store holds, plus the mix and growth behind those counts.

        `facts` and `retired` count live and retired facts across the whole
        store; everything else is scoped to the `days` window.
        """
        name = request.path_params["profile"]
        if not authorize(registry, name, request.headers.get("authorization")):
            return unauthorized()
        try:
            days = _positive_int(request.query_params.get("days", 30), 365)
        except ValueError:
            return JSONResponse({"error": "invalid days"}, status_code=400)
        conn = registry.connect(name)
        try:
            body = fact_stats(conn, days=days)
        finally:
            conn.close()
        return JSONResponse({"profile": name, **body})

    async def queries(request):
        """What has been asked of this profile's memory, newest first.

        Read-only and on the REST side rather than as a sixth MCP tool: this is
        for a human reviewing what the store failed to answer, and every tool
        description costs context in every agent session.
        """
        name = request.path_params["profile"]
        if not authorize(registry, name, request.headers.get("authorization")):
            return unauthorized()
        try:
            limit = _positive_int(request.query_params.get("limit", 50), 500)
        except ValueError:
            return JSONResponse({"error": "invalid limit"}, status_code=400)
        conn = registry.connect(name)
        try:
            entries = [asdict(e) for e in recent_queries(conn, limit=limit)]
        finally:
            conn.close()
        return JSONResponse({"profile": name, "queries": entries})

    async def queries_summary(request):
        """The same log, aggregated over a window rather than listed.

        Aggregating server-side rather than in the client is what makes the
        window honest: `/queries` is capped at 500 newest rows, so a chart
        built from it would silently describe a shorter period than its label.
        """
        name = request.path_params["profile"]
        if not authorize(registry, name, request.headers.get("authorization")):
            return unauthorized()
        try:
            days = _positive_int(request.query_params.get("days", 30), 365)
        except ValueError:
            return JSONResponse({"error": "invalid days"}, status_code=400)
        conn = registry.connect(name)
        try:
            body = query_summary(conn, days=days)
        finally:
            conn.close()
        return JSONResponse({"profile": name, **body})

    async def facts(request):
        """A page of live facts, either most-recent-first or hybrid-searched.

        This is the human-facing surface the client's list page reads, which is
        why pagination lives here rather than on an MCP tool: agents do not
        page, and every parameter description costs context in every session.
        It also means a human browsing their own store does not pollute the
        query log the way an MCP `memory_search` would.
        """
        name = request.path_params["profile"]
        if not authorize(registry, name, request.headers.get("authorization")):
            return unauthorized()
        try:
            limit = _positive_int(request.query_params.get("limit", 50), 200)
            offset = _non_negative_int(request.query_params.get("offset", 0),
                                       _SEARCH_PAGING_CAP)
        except ValueError:
            return JSONResponse({"error": "invalid limit or offset"},
                                status_code=400)
        q = request.query_params.get("q", "").strip()

        conn = registry.connect(name)
        try:
            if q == "":
                repo = FactsRepo(conn, embedder)
                page = [asdict(f) for f in repo.recent(limit=limit,
                                                       offset=offset)]
                total = repo.count_live()
            elif embedder is None:
                # The build omitted an embedder (unit tests often do). Search
                # cannot run without one; refuse rather than return a quiet
                # empty page that looks like "no matches".
                return JSONResponse(
                    {"error": "search is not configured on this server"},
                    status_code=501)
            else:
                pool = min(offset + limit, _SEARCH_PAGING_CAP)
                hits, matched = hybrid_search_with_stats(
                    conn, embedder, q, limit=pool)
                page = [asdict(h) for h in hits[offset:offset + limit]]
                total = matched
        finally:
            conn.close()

        return JSONResponse({"profile": name, "q": q, "limit": limit,
                             "offset": offset, "total": total,
                             "facts": page})

    return Starlette(routes=[
        Route("/health", health),
        Route("/api/profiles", profiles),
        Route("/api/{profile}/stats", stats),
        Route("/api/{profile}/queries", queries),
        Route("/api/{profile}/queries/summary", queries_summary),
        Route("/api/{profile}/facts", facts),
    ])
