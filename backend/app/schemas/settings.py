from pydantic import BaseModel


class SystemSettingsOut(BaseModel):
    open_access: bool
    allow_registration: bool
    token_default_daily_limit: int
    anonymous_ip_rate_limit_per_min: int
    vocab_max_items_per_owner: int | None
    site_name: str


class PublicSettingsOut(BaseModel):
    """匿名可见的系统设置子集，供前台页面决定是否展示登录墙、站点名称等。"""

    open_access: bool
    allow_registration: bool
    site_name: str
    initialized: bool


class SystemSettingsUpdateRequest(BaseModel):
    open_access: bool | None = None
    allow_registration: bool | None = None
    token_default_daily_limit: int | None = None
    anonymous_ip_rate_limit_per_min: int | None = None
    vocab_max_items_per_owner: int | None = None
    site_name: str | None = None
