"""网页端会话 cookie（对齐 cal 的 cookie 策略）。

为什么不再只靠 localStorage 里的 refresh token：
原先前端把 access(2h) / refresh(30d) 都放 localStorage，且**从不调用 /auth/refresh**，
所以 access 一过期（2 小时）就被 401 打回登录页——表现为「登录有效时间非常短」。

这里把 refresh token 放进 HttpOnly cookie（JS 读不到，防 XSS 窃取），有效期 7 天，
每次 /auth/refresh 都重发一次 cookie 实现滑动续期。属性参考 cal：
  Path=/（整站共用）
  HttpOnly（不可被 JS 读取）
  SameSite=Lax（挡跨站 POST；不用 Strict，免得从外部链接点进来丢会话）
  Secure 仅在请求确实是 HTTPS 时加（反代终止 TLS 时看 X-Forwarded-Proto；
  局域网 http 访问无条件加会导致浏览器不存 cookie，反而立刻掉登录）
"""

import ipaddress

from fastapi import Request, Response

from app.core.security import SESSION_COOKIE_TTL

USER_SESSION_COOKIE = "mydict_session"
ADMIN_SESSION_COOKIE = "mydict_admin_session"


def _is_trusted_proxy_peer(request: Request) -> bool:
    """直连对端是不是可信代理（本机/内网）。

    X-Forwarded-Proto 是客户端可伪造的头；只有当直连对端本身是反代（回环或私网地址）
    时才采信它，否则一律以 uvicorn 实际看到的 scheme 为准。
    """
    host = request.client.host if request.client else ""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private


def is_https_request(request: Request) -> bool:
    """判断外部访问是否是 HTTPS（反代终止 TLS 时 request.url.scheme 会是 http）。"""
    if request.url.scheme == "https":
        return True
    if not _is_trusted_proxy_peer(request):
        return False
    forwarded = request.headers.get("x-forwarded-proto") or request.headers.get("x-real-proto")
    if forwarded:
        # 多级代理时形如 "https, http"，以第一段为准
        return forwarded.split(",")[0].strip().lower() == "https"
    return False


def set_session_cookie(response: Response, name: str, token: str, request: Request) -> None:
    response.set_cookie(
        key=name,
        value=token,
        max_age=int(SESSION_COOKIE_TTL.total_seconds()),
        path="/",
        httponly=True,
        samesite="lax",
        secure=is_https_request(request),
    )


def clear_session_cookie(response: Response, name: str, request: Request) -> None:
    response.delete_cookie(
        key=name,
        path="/",
        httponly=True,
        samesite="lax",
        secure=is_https_request(request),
    )
