from pydantic import BaseModel, Field


class SystemSettingsOut(BaseModel):
    open_access: bool
    allow_registration: bool
    spx_online_transcode: bool
    token_default_daily_limit: int
    anonymous_ip_rate_limit_per_min: int
    user_ip_rate_limit_per_min: int
    vocab_max_items_per_owner: int | None
    site_name: str
    search_hint_text: str


class SpxTranscodeStatusOut(BaseModel):
    """发音实时转码的运行状态。

    available 为 false 表示容器里没有可用的 ffmpeg（它不随镜像分发，需要自行挂载），
    此时无论开关怎么设都不会转码。
    """

    available: bool
    ffmpeg_path: str | None
    ffmpeg_version: str | None
    converted: int
    failed: int
    max_concurrent: int


class PublicSettingsOut(BaseModel):
    """匿名可见的系统设置子集，供前台页面决定是否展示登录墙、站点名称等。"""

    open_access: bool
    allow_registration: bool
    site_name: str
    initialized: bool
    search_hint_text: str


class SystemSettingsUpdateRequest(BaseModel):
    open_access: bool | None = None
    allow_registration: bool | None = None
    spx_online_transcode: bool | None = None
    token_default_daily_limit: int | None = None
    anonymous_ip_rate_limit_per_min: int | None = None
    user_ip_rate_limit_per_min: int | None = None
    vocab_max_items_per_owner: int | None = None
    site_name: str | None = None
    search_hint_text: str | None = Field(default=None, max_length=100)
