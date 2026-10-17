from pydantic import BaseModel


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    # 网页端刷新凭证放在 HttpOnly cookie 里，请求体可以为空；桌面端/扩展仍可显式传。
    refresh_token: str | None = None
