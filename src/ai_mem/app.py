from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount

from ai_mem.api import build_api
from ai_mem.auth import UNAUTHORIZED_BODY, authorize, header_value
from ai_mem.config import Settings
from ai_mem.embedding import Embedder
from ai_mem.mcp_server import build_mcp
from ai_mem.profile_context import reset_profile, set_profile
from ai_mem.profiles import ProfileRegistry


class ProfileDispatcher:
    """Strips the leading path segment, validates it as a profile, and binds
    it to a ContextVar for the duration of the request.

    Starlette's Mount does not support path parameters, so this is a small
    ASGI wrapper rather than routing. Validation happens here so an unknown or
    unsafe or unauthorised profile is refused before reaching any tool — and,
    critically, before anything could create a database for it.
    """

    def __init__(self, inner, registry: ProfileRegistry) -> None:
        self.inner = inner
        self.registry = registry

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.inner(scope, receive, send)
            return

        # Starlette versions differ on whether Mount strips its prefix from
        # scope["path"] or only records it in root_path. Derive the relative
        # path from both so this works either way.
        prefix = scope.get("root_path") or ""
        full = scope["path"]
        relative = full[len(prefix):] if prefix and full.startswith(prefix) else full

        name, _, rest = relative.lstrip("/").partition("/")

        # One check covers existence and authorisation, and one response
        # covers every failure — a distinct 404 for "no such profile" would
        # let anyone on the network enumerate profile names.
        if not authorize(self.registry, name, header_value(scope, "authorization")):
            await JSONResponse(
                UNAUTHORIZED_BODY, status_code=401)(scope, receive, send)
            return

        # Hand the inner app a clean absolute path with no mount prefix.
        inner_path = "/" + rest
        scope = dict(scope, path=inner_path, raw_path=inner_path.encode(),
                     root_path="")
        token = set_profile(name)
        try:
            await self.inner(scope, receive, send)
        finally:
            reset_profile(token)


def build_app(settings: Settings):
    registry = ProfileRegistry(settings.data_dir)
    embedder = Embedder(settings.embed_model)
    mcp_app = build_mcp(registry, embedder, settings).http_app(path="/")

    return Starlette(
        routes=[
            Mount("/mcp", app=ProfileDispatcher(mcp_app, registry)),
            Mount("/", app=build_api(registry)),
        ],
        lifespan=mcp_app.lifespan,
    )
