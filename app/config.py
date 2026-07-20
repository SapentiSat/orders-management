from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Orders Management"
    app_env: str = "development"
    secret_key: str = "change-me-in-production"
    license_signing_secret: str = "om-dev-signing-secret-change-in-prod"
    license_key: str = ""
    data_dir: Path = Path("data")
    sample_mode: bool = True
    host: str = "0.0.0.0"
    port: int = 8000

    @property
    def runtime_dir(self) -> Path:
        return self.data_dir / "runtime"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def settings_file(self) -> Path:
        return self.runtime_dir / "settings.json"

    @property
    def license_file(self) -> Path:
        return self.runtime_dir / "license.key"


def get_settings() -> Settings:
    return Settings()


def ensure_dirs(settings: Settings) -> None:
    for path in (
        settings.data_dir,
        settings.runtime_dir,
        settings.exports_dir,
        settings.logs_dir,
        settings.uploads_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)
