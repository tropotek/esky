from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from ai_mem.profiles import InvalidProfileName, UnknownProfile


def build_api(registry) -> Starlette:
    async def health(request):
        return JSONResponse({"status": "ok"})

    async def profiles(request):
        return JSONResponse({"profiles": registry.list()})

    async def stats(request):
        name = request.path_params["profile"]
        try:
            conn = registry.connect(name)
        except (UnknownProfile, InvalidProfileName):
            return JSONResponse({"error": "unknown profile"}, status_code=404)
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
