from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import ValidationAppError
from app.services import settings_service
from app.services.admin_auth_service import is_initialized
from app.services.audit_service import log_action
from app.services.online_dict_service import SOURCE_IDS

_BOOL_KEYS = {"open_access", "allow_registration", "online_dict_enabled"}
_INT_KEYS = {
    "token_default_daily_limit",
    "anonymous_ip_rate_limit_per_min",
    "user_ip_rate_limit_per_min",
}
_OPTIONAL_INT_KEYS = {"vocab_max_items_per_owner"}
_STR_KEYS = {"site_name", "search_hint_text", "online_dict_sources"}

_SEARCH_HINT_DEFAULT = "小搜一下, 大进一步"



def _normalize_online_sources(raw: str | None) -> str:
    """把用户输入的 CSV 归一化成固定顺序的白名单 CSV；非法 id 忽略，空值 = 全部启用。"""
    if not raw:
        return ""
    picked = {sid.strip() for sid in raw.split(",")}
    return ",".join(sid for sid in SOURCE_IDS if sid in picked)


def _normalize_proxy(raw: str | None) -> str:
    """出站代理只接受 http(s)://host[:port]：httpx 未装 socks 扩展，其它写法每次请求都会失败。"""
    value = (raw or "").strip()
    if not value:
        return ""
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValidationAppError("出站代理须为 http:// 或 https:// 开头的地址，如 http://127.0.0.1:7890")
    return value


def _save_online_dict_proxy(db: Session, raw: str | None, defaults: Settings) -> str:
    """与部署环境变量 ONLINE_DICT_PROXY 相同（含都为空）时删掉覆盖项、回落到 env；
    否则存为覆盖值——空串表示在 env 配了代理的部署上改为直连。"""
    value = _normalize_proxy(raw)
    if value == defaults.online_dict_proxy.strip():
        settings_service.delete_setting(db, "online_dict_proxy")
    else:
        settings_service.set_setting(db, "online_dict_proxy", value)
    return value


def get_all_settings(db: Session, defaults: Settings) -> dict:
    return {
        "open_access": settings_service.get_bool_setting(
            db, "open_access", defaults.open_access_default
        ),
        "allow_registration": settings_service.get_bool_setting(
            db, "allow_registration", defaults.allow_registration_default
        ),
        # 在线词典总开关：默认禁用（出站抓取第三方站点，是否开放由部署者决定）
        "online_dict_enabled": settings_service.get_bool_setting(
            db, "online_dict_enabled", False
        ),
        "token_default_daily_limit": settings_service.get_int_setting(
            db, "token_default_daily_limit", defaults.token_default_daily_limit
        ),
        "anonymous_ip_rate_limit_per_min": settings_service.get_int_setting(
            db, "anonymous_ip_rate_limit_per_min", defaults.anonymous_ip_rate_limit_per_min
        ),
        "user_ip_rate_limit_per_min": settings_service.get_int_setting(
            db, "user_ip_rate_limit_per_min", defaults.user_ip_rate_limit_per_min
        ),
        "vocab_max_items_per_owner": _get_optional_int(db, "vocab_max_items_per_owner"),
        "site_name": settings_service.get_setting(db, "site_name", "MyDict"),
        "search_hint_text": settings_service.get_setting(
            db, "search_hint_text", _SEARCH_HINT_DEFAULT
        ),
        "online_dict_proxy": settings_service.get_setting(
            db, "online_dict_proxy", defaults.online_dict_proxy
        ),
        "online_dict_sources": _normalize_online_sources(
            settings_service.get_setting(db, "online_dict_sources", "")
        ),
    }


def get_public_settings(db: Session, defaults: Settings) -> dict:
    return {
        "open_access": settings_service.get_bool_setting(
            db, "open_access", defaults.open_access_default
        ),
        "allow_registration": settings_service.get_bool_setting(
            db, "allow_registration", defaults.allow_registration_default
        ),
        # 前台要靠它决定是否渲染【在线】标签
        "online_dict_enabled": settings_service.get_bool_setting(
            db, "online_dict_enabled", False
        ),
        "site_name": settings_service.get_setting(db, "site_name", "MyDict"),
        "initialized": is_initialized(db),
        "search_hint_text": settings_service.get_setting(
            db, "search_hint_text", _SEARCH_HINT_DEFAULT
        ),
    }


def _get_optional_int(db: Session, key: str) -> int | None:
    raw = settings_service.get_setting(db, key)
    if raw is None or not raw.strip():
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def update_settings(
    db: Session, updates: dict, fields_set: set[str], defaults: Settings, admin_id: int
) -> dict:
    """updates 中只处理 fields_set 里实际出现过的字段，区分「未传」与「显式传 null」。"""
    if "online_dict_proxy" in fields_set:
        # 逐项写库、各自 commit，先校验，免得非法代理报错时前面的字段已经存进去
        _normalize_proxy(updates.get("online_dict_proxy"))
    changed = {}
    for key in fields_set:
        if key == "online_dict_proxy":
            changed[key] = _save_online_dict_proxy(db, updates.get(key), defaults)
            continue
        if key not in _BOOL_KEYS | _INT_KEYS | _OPTIONAL_INT_KEYS | _STR_KEYS:
            continue
        value = updates.get(key)
        if key in _OPTIONAL_INT_KEYS:
            settings_service.set_setting(db, key, "" if value is None else str(value))
        elif key in _BOOL_KEYS:
            settings_service.set_setting(db, key, "true" if value else "false")
        elif key in _INT_KEYS:
            settings_service.set_setting(db, key, str(value))
        else:
            if key == "online_dict_sources":
                value = _normalize_online_sources(value)
            settings_service.set_setting(db, key, value or "")
        changed[key] = value

    if changed:
        log_action(
            db, actor_type="admin", actor_id=admin_id, action="settings.update", detail=changed
        )
    return get_all_settings(db, defaults)
