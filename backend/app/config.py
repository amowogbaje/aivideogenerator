from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/studio.db"
    DATA_DIR: str = "./data"

    TEXT_PROVIDER: str = "auto"
    IMAGE_PROVIDER: str = "auto"
    VOICE_PROVIDER: str = "auto"

    GEMINI_API_KEY: str = ""
    HF_API_KEY: str = ""
    DEEPINFRA_API_KEY: str = ""
    TOGETHER_API_KEY: str = ""
    ELEVENLABS_API_KEY: str = ""

    DEFAULT_ASPECT_RATIO: str = "9:16"
    IMAGE_CONCURRENCY: int = 2
    MAX_ATTEMPTS: int = 3

    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def data_path(self) -> Path:
        return Path(self.DATA_DIR).resolve()

    @property
    def media_path(self) -> Path:
        return self.data_path / "media"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
