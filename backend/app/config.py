from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CET-4 个人词库"
    database_url: str = "sqlite:////data/vocab.db"
    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    frontend_dist: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


settings = Settings()


def ensure_sqlite_directory() -> None:
    prefix = "sqlite:///"
    if settings.database_url.startswith(prefix):
        path = settings.database_url.removeprefix(prefix)
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
