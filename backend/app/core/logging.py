import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.core.config import get_settings

_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_MAX_BYTES = 5 * 1024 * 1024
_BACKUP_COUNT = 5


def configure_logging() -> None:
    settings = get_settings()
    formatter = logging.Formatter(_FORMAT)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    Path(settings.log_dir).mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        Path(settings.log_dir) / "mydict.log",
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.INFO)
    root.addHandler(stream_handler)
    root.addHandler(file_handler)
