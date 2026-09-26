from pydantic import BaseModel, Field


class SystemSettingsOut(BaseModel):
    open_access: bool
    allow_registration: bool
    online_dict_enabled: bool
    token_default_daily_limit: int
    anonymous_ip_rate_limit_per_min: int
    user_ip_rate_limit_per_min: int
    vocab_max_items_per_owner: int | None
    site_name: str
    search_hint_text: str
    online_dict_proxy: str
    online_dict_sources: str


class PublicSettingsOut(BaseModel):
    """匿名可见的系统设置子集，供前台页面决定是否展示登录墙、站点名称等。"""

    open_access: bool
    allow_registration: bool
    online_dict_enabled: bool
    site_name: str
    initialized: bool
    search_hint_text: str


class SystemSettingsUpdateRequest(BaseModel):
    open_access: bool | None = None
    allow_registration: bool | None = None
    online_dict_enabled: bool | None = None
    token_default_daily_limit: int | None = None
    anonymous_ip_rate_limit_per_min: int | None = None
    user_ip_rate_limit_per_min: int | None = None
    vocab_max_items_per_owner: int | None = None
    site_name: str | None = None
    search_hint_text: str | None = Field(default=None, max_length=100)
    online_dict_proxy: str | None = Field(default=None, max_length=300)
    online_dict_sources: str | None = Field(default=None, max_length=200)
