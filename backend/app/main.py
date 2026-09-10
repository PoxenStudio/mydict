from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse

from app.api.health import router as health_router
from app.core.config import get_settings

settings = get_settings()
settings.ensure_data_dirs()

app = FastAPI(title="MyDict")

app.include_router(health_router, prefix="/api")

static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str) -> FileResponse:
        candidate = static_dir / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(static_dir / "index.html")
