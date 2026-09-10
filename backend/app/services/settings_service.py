from sqlalchemy.orm import Session

from app.models.settings import SystemSetting

_TRUE_VALUES = {"true", "1", "yes"}


def get_setting(db: Session, key: str, default: str | None = None) -> str | None:
    row = db.get(SystemSetting, key)
    return row.value if row is not None else default


def get_bool_setting(db: Session, key: str, default: bool = False) -> bool:
    value = get_setting(db, key)
    if value is None:
        return default
    return value.lower() in _TRUE_VALUES


def get_int_setting(db: Session, key: str, default: int) -> int:
    value = get_setting(db, key)
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError:
        return default


def set_setting(db: Session, key: str, value: str) -> None:
    row = db.get(SystemSetting, key)
    if row is None:
        row = SystemSetting(key=key, value=value)
        db.add(row)
    else:
        row.value = value
    db.commit()
