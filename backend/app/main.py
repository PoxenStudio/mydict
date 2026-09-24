from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
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
from app.core.db import get_db
from app.core.exceptions import AppError, RateLimitedError
from app.core.logging import configure_logging
from app.core.migrate import run_migrations
from app.core.version import get_app_version
from app.services import spx_transcode
from app.services.resource_service import (
    normalize_resource_path,
    resolve_resource_file,
    strip_legacy_file_prefix,
)

from app.services.settings_service import get_bool_setting
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


def _transcode_spx_on_demand(db: Session, target: Path) -> Path | None:
    """请求的 mp3 不存在时，看能不能拿同名的 .spx 现转一个出来。

    要在四个条件都满足时才动手：请求的就是 .mp3、同名 .spx 在场、后台开关开着、容器里
    能找到 ffmpeg。任一不满足就返回 None，让调用方照旧 404——前端会回退到原文件并提示
    「这个格式放不了」，与没有这个功能时表现一致。
    """
    if target.suffix.lower() != ".mp3":
        return None
    source = target.with_suffix(".spx")
    if not source.is_file():
        return None
    if not get_bool_setting(db, "spx_online_transcode", True):
        return None
    return spx_transcode.transcode_to_mp3(source)


@app.get("/dict-res/{dictionary_id}/res/{resource_path:path}")
def dict_resource(
    dictionary_id: int, resource_path: str, db: Session = Depends(get_db)
) -> FileResponse:
    """只读对外暴露词典 res/ 子目录；source/ 原始文件不经此路由可达。

    必须带 Access-Control-Allow-Origin：词条 iframe 用 sandbox="allow-scripts"
    （不含 allow-same-origin），它是不透明源，加载这里的 @font-face 与 XHR 都算跨域，
    没有这个头会**静默失败** —— 表现为词典自带字体/样式无声失效。资源本身是公开只读的，
    放开跨域没有问题。

    少部分发音是 Speex（.spx），浏览器放不了；前端会先来要同名 .mp3，这里在它不存在时
    按需转一个（见 `_transcode_spx_on_demand`）。

    路径解析交给 `resolve_resource_file`：它除了精确匹配，还会兼容历史坏链接里多出来的
    `file:/` 前缀、并按大小写不敏感兜底（词典多在 Windows 上打包，引用常与 `.mdd` 里的
    键大小写不一致）。
    """
    try:
        normalized = normalize_resource_path(resource_path)
    except ValueError:
        raise HTTPException(status_code=404) from None
    # 历史坏链接：早期改写把 file:///down/x.gif 拼成了 res/file:/down/x.gif
    normalized = strip_legacy_file_prefix(normalized)
    res_dir = Path(settings.dictionary_storage_path) / str(dictionary_id) / "res"
    target = resolve_resource_file(res_dir, normalized)
    if target is None:
        # 按需转码放在大小写兜底之后：转出来的文件名与请求完全一致，精确匹配即可命中
        target = _transcode_spx_on_demand(db, res_dir / normalized)
        if target is None:
            raise HTTPException(status_code=404)
    return FileResponse(
        target,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=86400",
        },
    )


static_dir = Path(__file__).parent / "static"
if (static_dir / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str) -> FileResponse:
        candidate = static_dir / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(static_dir / "index.html")
