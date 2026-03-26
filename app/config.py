from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    env: str = "development"
    log_level: str = "INFO"

    # LLM — Groq
    openai_api_key: str
    openai_model: str = "llama-3.3-70b-versatile"
    openai_base_url: str = "https://api.groq.com/openai/v1"

    # Database
    database_url: str

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # LinkedIn
    linkedin_email: str = ""
    linkedin_password: str = ""

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
