from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str
    AI_PROVIDER: str = "fal"  # Options: "fal", "deepinfra", "together", "huggingface"
    DEEPINFRA_API_KEY: str = ""
    TOGETHER_API_KEY: str = ""
    HF_API_KEY: str = ""
    OPENAI_API_KEY: str = "mock"
    GEMINI_API_KEY: str = "mock"
    FAL_AI_API_KEY: str = "mock"
    LUMA_API_KEY: str = "mock"

    AUDIO_AI_PROVIDER: str = "elevenlabs"  # Options: "elevenlabs", "edgetts"
    ELEVENLABS_API_KEY: str = "mock"

    
    MOCK_AI: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()