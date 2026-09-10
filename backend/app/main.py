from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse

from app.api.admin.auth import router as admin_auth_router
from app.api.health import router as health_router
from app.api.web.auth import router as web_auth_router
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.migrate import run_migrations

settings = get_settings()
settings.ensure_data_dirs()
run_migrations()

app = FastAPI(title="MyDict")


@app.exception_handler(AppError)
def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message, "detail": exc.detail},
    )


app.include_router(health_router, prefix="/api")
app.include_router(admin_auth_router, prefix="/api")
app.include_router(web_auth_router, prefix="/api")

static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str) -> FileResponse:
        candidate = static_dir / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(static_dir / "index.html")
