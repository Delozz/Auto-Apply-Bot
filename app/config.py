from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    env: str = "development"
    log_level: str = "INFO"

    # LLM — Groq
    openai_api_key: str
    openai_model: str = "llama-3.3-70b-versatile"
    vision_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    openai_base_url: str = "https://api.groq.com/openai/v1"

    # Database
    database_url: str
    postgres_user: str = "devon"
    postgres_password: str
    postgres_db: str = "auto_apply"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # LinkedIn
    linkedin_email: str = ""
    linkedin_password: str = ""

    # Gmail — for reading verification codes sent to the application email
    gmail_address: str = "devoninternships@gmail.com"
    gmail_app_password: str = ""  # generate at myaccount.google.com/apppasswords

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()