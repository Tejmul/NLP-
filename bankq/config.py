"""Application settings, read from environment variables (prefix BANKQ_) or a .env file."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BANKQ_", env_file=ROOT / ".env", extra="ignore")

    env: str = "dev"
    log_level: str = "INFO"
    log_json: bool = True

    database_url: str = f"sqlite:///{ROOT / 'data' / 'bankq.db'}"
    registry_dir: Path = ROOT / "models" / "registry"
    rules_path: Path = ROOT / "configs" / "routing_rules.yaml"
    raw_data_dir: Path = ROOT / "data" / "raw"
    processed_data_dir: Path = ROOT / "data" / "processed"
    reports_dir: Path = ROOT / "reports"

    # Comma-separated keys. Empty means auth is off (local development only).
    api_keys: str = ""
    rate_limit_per_minute: int = 120
    max_batch_size: int = 1000

    @property
    def api_key_set(self) -> set[str]:
        return {k.strip() for k in self.api_keys.split(",") if k.strip()}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
