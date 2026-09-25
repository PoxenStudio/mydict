from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core import bootstrap

_MESSAGE = "系统正在升级，请稍后再试"


def _blocked(path: str) -> bool:
    if not path.startswith("/api/") or path == "/api/health":
        return False
    return not path.startswith("/api/system/")


class MaintenanceGate:
    """启动流程未就绪时，/api 下除健康检查与系统状态外一律 503。

    迁移期间 SQLite 被独占，放过任何业务请求都只会卡住或报锁错误。静态页面与 /dict-res
    只读文件、不碰数据库，照常放行，前端才能加载出来展示维护提示。
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and not bootstrap.is_ready() and _blocked(scope["path"]):
            response = JSONResponse(
                status_code=503,
                content={"code": "maintenance", "message": _MESSAGE, "detail": None},
                headers={"Retry-After": "5"},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
