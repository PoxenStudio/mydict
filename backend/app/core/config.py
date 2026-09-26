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
    user_ip_rate_limit_per_min: int = 120
    max_upload_size_mb: int = 512
    enable_scheduler: bool = True
    # 「一天」的划分时区；留空或无效时回落系统时区
    timezone: str = ""
    version_file_path: str = "/version.txt"

    config_storage_path: str = "/data/config"
    dicts_inbox_path: str = "/data/dicts"
    database_path: str = "/data/db/mydict.sqlite3"
    dictionary_storage_path: str = "/data/dictionaries"
    log_dir: str = "/data/logs"

    # 在线词典出站抓取（维基百科/维基词典）用的 HTTP 代理；留空直连。
    # 这台部署环境直连维基不可达，需要走本网段的代理（如 http://192.168.5.197:7890）。
    online_dict_proxy: str = ""

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
