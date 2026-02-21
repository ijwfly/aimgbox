from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route


async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "admin"})


def create_admin_app() -> Starlette:
    routes = [
        Route("/health", health, methods=["GET"]),
    ]
    return Starlette(routes=routes)
