from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    database_url: str = f"sqlite:///{(ROOT / 'data' / 'tracker.db').as_posix()}"
    fx_api_url: str = "https://api.frankfurter.dev/v1"
    ebay_app_id: str = ""
    xianyu_cookie: str = ""
    collect_cron_hour: int = 0
    collect_cron_minute: int = 0
    collect_on_startup: bool = False
    signature_usd_min: float = 300.0
    signature_usd_max: float = 8000.0
    player_usd_min: float = 20.0
    player_usd_max: float = 250.0
    request_timeout: float = 25.0


settings = Settings()
