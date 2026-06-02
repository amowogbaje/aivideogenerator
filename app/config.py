from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str
    
    OPENAI_API_KEY: str = "mock"
    GEMINI_API_KEY: str = "mock"
    ELEVENLABS_API_KEY: str = "mock"
    FAL_AI_API_KEY: str = "mock"
    LUMA_API_KEY: str = "mock"
    
    MOCK_AI: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()