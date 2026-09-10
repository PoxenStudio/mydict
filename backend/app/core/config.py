from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    jwt_secret: str = ""
    open_access_default: bool = False
    allow_registration_default: bool = True
    token_default_daily_limit: int = 1000
    anonymous_ip_rate_limit_per_min: int = 60
    max_upload_size_mb: int = 512
    enable_scheduler: bool = True
    version_file_path: str = "/version.txt"

    config_storage_path: str = "/data/config"
    dicts_inbox_path: str = "/data/dicts"
    database_path: str = "/data/db/mydict.sqlite3"
    dictionary_storage_path: str = "/data/dictionaries"
    log_dir: str = "/data/logs"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path}"

    def ensure_data_dirs(self) -> None:
        for path in (
            self.config_storage_path,
            self.dicts_inbox_path,
            Path(self.database_path).parent,
            self.dictionary_storage_path,
            self.log_dir,
        ):
            Path(path).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
