from pydantic import BaseModel


class TokenPairResponse(BaseModel):
    access_token: str
    # 网页端（凭证取自 HttpOnly cookie）刷新时不回显 refresh token，避免把受保护的
    # 凭证又交还给页面脚本；桌面端/扩展显式传 token 时照旧返回。
    refresh_token: str | None = None
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    # 网页端刷新凭证放在 HttpOnly cookie 里，请求体可以为空；桌面端/扩展仍可显式传。
    refresh_token: str | None = None
