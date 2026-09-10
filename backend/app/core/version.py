from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings

DEFAULT_VERSION = "dev"


@lru_cache
def get_app_version() -> str:
    try:
        content = Path(get_settings().version_file_path).read_text(encoding="utf-8").strip()
    except OSError:
        return DEFAULT_VERSION
    return content or DEFAULT_VERSION
