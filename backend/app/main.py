from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse

from app.api.admin.auth import router as admin_auth_router
from app.api.admin.dictionaries import router as admin_dictionaries_router
from app.api.admin.settings import router as admin_settings_router
from app.api.admin.stats import router as admin_stats_router
from app.api.admin.tasks import router as admin_tasks_router
from app.api.admin.tokens import router as admin_tokens_router
from app.api.admin.users import router as admin_users_router
from app.api.health import router as health_router
from app.api.system import router as system_router
from app.api.v1.query import router as v1_query_router
from app.api.v1.vocab import router as v1_vocab_router
from app.api.web.auth import router as web_auth_router
from app.api.web.dict import router as web_dict_router
from app.api.web.public_settings import router as web_public_settings_router
from app.api.web.vocab import router as web_vocab_router
from app.core.config import get_settings
from app.core.exceptions import AppError, RateLimitedError
from app.core.logging import configure_logging
from app.core.migrate import run_migrations
from app.core.version import get_app_version
from app.services.resource_service import normalize_resource_path
from app.tasks.scheduler import start_scheduler

settings = get_settings()
settings.ensure_data_dirs()
get_app_version()
run_migrations()
# alembic 迁移会通过 fileConfig 重新配置 root logger（见 alembic/env.py），
# 必须放在 run_migrations() 之后调用才不会被它覆盖掉
configure_logging()
if settings.enable_scheduler:
    start_scheduler()

app = FastAPI(title="MyDict")


@app.exception_handler(AppError)
def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    headers = {"Retry-After": str(exc.retry_after)} if isinstance(exc, RateLimitedError) else None
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message, "detail": exc.detail},
        headers=headers,
    )


app.include_router(health_router, prefix="/api")
app.include_router(system_router, prefix="/api")
app.include_router(admin_auth_router, prefix="/api")
app.include_router(web_auth_router, prefix="/api")
app.include_router(admin_dictionaries_router, prefix="/api")
app.include_router(admin_tokens_router, prefix="/api")
app.include_router(admin_users_router, prefix="/api")
app.include_router(admin_settings_router, prefix="/api")
app.include_router(admin_stats_router, prefix="/api")
app.include_router(admin_tasks_router, prefix="/api")
app.include_router(v1_query_router, prefix="/api")
app.include_router(v1_vocab_router, prefix="/api")
app.include_router(web_dict_router, prefix="/api")
app.include_router(web_vocab_router, prefix="/api")
app.include_router(web_public_settings_router, prefix="/api")


@app.get("/dict-res/{dictionary_id}/res/{resource_path:path}")
def dict_resource(dictionary_id: int, resource_path: str) -> FileResponse:
    """只读对外暴露词典 res/ 子目录；source/ 原始文件不经此路由可达。"""
    try:
        normalized = normalize_resource_path(resource_path)
    except ValueError:
        raise HTTPException(status_code=404) from None
    target = Path(settings.dictionary_storage_path) / str(dictionary_id) / "res" / normalized
    if not target.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(target)


static_dir = Path(__file__).parent / "static"
if (static_dir / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str) -> FileResponse:
        candidate = static_dir / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(static_dir / "index.html")
