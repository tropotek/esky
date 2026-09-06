from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from esky.auth import UNAUTHORIZED_BODY, authorize


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
        name = request.path_params["profile"]
        if not authorize(registry, name, request.headers.get("authorization")):
            return unauthorized()
        conn = registry.connect(name)
        try:
            facts = conn.execute(
                "SELECT count(*) FROM facts WHERE retired_at IS NULL").fetchone()[0]
            retired = conn.execute(
                "SELECT count(*) FROM facts WHERE retired_at IS NOT NULL").fetchone()[0]
        finally:
            conn.close()
        return JSONResponse({"profile": name, "facts": facts, "retired": retired})

    return Starlette(routes=[
        Route("/health", health),
        Route("/api/profiles", profiles),
        Route("/api/{profile}/stats", stats),
    ])
