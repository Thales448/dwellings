from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse

from app.auth.passkey_routes import router as passkey_router
from app.auth.routes import router as auth_router
from app.core.config import get_settings
from app.core.health import health_payload
from app.core.security import SecurityMiddleware


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Dwellings")
    app.add_middleware(SecurityMiddleware)
    app.include_router(auth_router)
    app.include_router(passkey_router)

    @app.get("/api/v1/health")
    def health() -> JSONResponse:
        body, code = health_payload(settings)
        return JSONResponse(body, status_code=code)

    static = settings.resolved_static_dir
    if static is not None:
        index = static / "index.html"

        def _file_for(full_path: str) -> FileResponse | JSONResponse:
            root = static.resolve()
            candidate = (static / full_path).resolve()
            if root == candidate or root in candidate.parents:
                if candidate.is_file():
                    return FileResponse(candidate)
            if index.is_file():
                return FileResponse(index)
            return JSONResponse({"detail": "not found"}, status_code=404)

        @app.get("/", include_in_schema=False, response_model=None)
        def spa_root() -> FileResponse | JSONResponse:
            return _file_for("index.html")

        @app.get("/{full_path:path}", include_in_schema=False, response_model=None)
        def spa(full_path: str) -> FileResponse | JSONResponse:
            if full_path.startswith("api/"):
                return JSONResponse({"detail": "not found"}, status_code=404)
            return _file_for(full_path)

    return app


app = create_app()


def static_root() -> Path | None:
    return get_settings().resolved_static_dir
