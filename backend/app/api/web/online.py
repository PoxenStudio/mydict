"""在线词典查询端点（维基百科 / 维基词典 / 百度百科 / 外部搜索链接）。

出站抓取在本服务端做（百度百科无 CORS 且要求手机 UA；维基两家的 REST 接口虽然
CORS 开放，但统一走服务端可以加缓存、限流，也避免把用户 IP 直接暴露给第三方）。
返回的是**纯文本**结构化结果——第三方 HTML 不进前端，没有注入面。

不计入查询配额：它不是词典查询，走独立的按 IP 限额（与词条文档同量级），防止
被当成匿名抓取代理。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.web.dict import _ip_rate_limit
from app.core import rate_limiter
from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.deps import WebCaller, get_web_caller
from app.core.exceptions import ForbiddenError, RateLimitedError
from app.schemas.query import OnlineLookupResponse
from app.services import online_dict_service, settings_service
router = APIRouter(prefix="/dict", tags=["web-dict"])

# 在线抓取比本地查询贵得多（出站 HTTP + 第三方站点的耐受度），限额收紧到按 IP
# 查询限额的一半。与词条文档的乘数做法相反——那里是放大（它是已计费查询的子
# 请求），这里是缩小（它是独立的出站行为）。
_ONLINE_RATE_DIVISOR = 2


@router.get("/online/lookup", response_model=OnlineLookupResponse)
def online_lookup(
    word: str,
    lang: str = Query("zh", pattern="^[a-z]{2}(-[A-Za-z]{2,4})?$"),
    caller: WebCaller = Depends(get_web_caller),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> OnlineLookupResponse:
    counter_key, limit = _ip_rate_limit(db, caller, settings)
    if not rate_limiter.check_and_increment(
        f"online:{counter_key}", max(5, limit // _ONLINE_RATE_DIVISOR)
    ):
        raise RateLimitedError(
            "在线词典查询过于频繁，请稍后再试",
            retry_after=rate_limiter.seconds_to_next_minute(),
        )

    # 总开关：管理后台默认禁用；关着时端点直接拒绝（前端标签也已隐藏，这里是双保险）
    if not settings_service.get_bool_setting(db, "online_dict_enabled", False):
        raise ForbiddenError("在线词典功能未启用，请联系管理员在系统设置中开启")

    # 出站代理：管理后台设置（DB）覆盖 env 默认值，热同步（变了才动，免得反复清缓存）
    proxy = settings_service.get_setting(
        db, "online_dict_proxy", settings.online_dict_proxy
    ).strip()
    if proxy != online_dict_service.active_proxy():
        online_dict_service.configure_proxy(proxy or None)

    word = word.strip()[:100]
    if not word:
        return OnlineLookupResponse(word=word, lang=lang, sections=[], links=[])

    # 源开关：管理后台「在线词典」的启用白名单（CSV；空 = 全部启用）
    raw = settings_service.get_setting(db, "online_dict_sources", "").strip()
    enabled = {sid for sid in raw.split(",") if sid in online_dict_service.ALL_SOURCE_IDS}
    data = online_dict_service.lookup_online(word, lang, enabled or None)
    return OnlineLookupResponse(**data)
