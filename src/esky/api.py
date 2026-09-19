from dataclasses import asdict

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from esky.auth import UNAUTHORIZED_BODY, authorize
from esky.metrics import fact_stats, query_summary
from esky.querylog import recent_queries


def _positive_int(value, maximum: int) -> int:
    """Parse a caller-supplied count, refusing anything SQLite would misread.

    A negative LIMIT means 'no limit' in SQLite, so an unchecked value is not
    merely odd — it silently defeats the cap it was supposed to be bounded by.
    """
    number = int(value)
    if number < 1:
        raise ValueError(number)
    return min(number, maximum)


def build_api(registry) -> Starlette:
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

    return Starlette(routes=[
        Route("/health", health),
        Route("/api/profiles", profiles),
        Route("/api/{profile}/stats", stats),
        Route("/api/{profile}/queries", queries),
        Route("/api/{profile}/queries/summary", queries_summary),
    ])
