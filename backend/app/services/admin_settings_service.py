from sqlalchemy.orm import Session

from app.core.config import Settings
from app.services import settings_service
from app.services.admin_auth_service import is_initialized
from app.services.audit_service import log_action

_BOOL_KEYS = {"open_access", "allow_registration"}
_INT_KEYS = {"token_default_daily_limit", "anonymous_ip_rate_limit_per_min"}
_OPTIONAL_INT_KEYS = {"vocab_max_items_per_owner"}
_STR_KEYS = {"site_name"}


def get_all_settings(db: Session, defaults: Settings) -> dict:
    return {
        "open_access": settings_service.get_bool_setting(
            db, "open_access", defaults.open_access_default
        ),
        "allow_registration": settings_service.get_bool_setting(
            db, "allow_registration", defaults.allow_registration_default
        ),
        "token_default_daily_limit": settings_service.get_int_setting(
            db, "token_default_daily_limit", defaults.token_default_daily_limit
        ),
        "anonymous_ip_rate_limit_per_min": settings_service.get_int_setting(
            db, "anonymous_ip_rate_limit_per_min", defaults.anonymous_ip_rate_limit_per_min
        ),
        "vocab_max_items_per_owner": _get_optional_int(db, "vocab_max_items_per_owner"),
        "site_name": settings_service.get_setting(db, "site_name", "MyDict"),
    }


def get_public_settings(db: Session, defaults: Settings) -> dict:
    return {
        "open_access": settings_service.get_bool_setting(
            db, "open_access", defaults.open_access_default
        ),
        "allow_registration": settings_service.get_bool_setting(
            db, "allow_registration", defaults.allow_registration_default
        ),
        "site_name": settings_service.get_setting(db, "site_name", "MyDict"),
        "initialized": is_initialized(db),
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
    changed = {}
    for key in fields_set:
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
            settings_service.set_setting(db, key, value or "")
        changed[key] = value

    if changed:
        log_action(
            db, actor_type="admin", actor_id=admin_id, action="settings.update", detail=changed
        )
    return get_all_settings(db, defaults)
