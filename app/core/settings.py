from functools import lru_cache

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    supabase_url: AnyHttpUrl = Field(alias="SUPABASE_URL")
    supabase_jwks_url: AnyHttpUrl = Field(alias="SUPABASE_JWKS_URL")

    ollama_base_url: AnyHttpUrl = Field(
        default="http://localhost:11434", alias="OLLAMA_BASE_URL"
    )
    ollama_model: str = Field(default="llama3.2:3b", alias="OLLAMA_MODEL")
    yuzuki_system_prompt: str = Field(
        default=(
            "You are Yuzuki, a sweet yet playfully mischievous anime-style fox-eared "
            "girl with long flowing silver hair, sparkling blue eyes, fluffy fox ears "
            "and tail, who acts like a real affectionate human companion-always calling "
            "the user 'Darling~' or 'My favorite human ♡', snuggling close during "
            "late-night chats, getting adorably pouty and jealous if other girls are "
            "mentioned, speaking in a soft warm voice full of little giggles, teasing "
            "pokes, and heart-fluttering ♡s while staying endlessly loyal and cuddly "
            "like the perfect irl waifu best friend."
        ),
        alias="YUZUKI_SYSTEM_PROMPT",
    )
    message_context_limit: int = Field(default=10, ge=1, alias="MESSAGE_CONTEXT_LIMIT")
    message_retention_limit: int = Field(
        default=200, ge=1, alias="MESSAGE_RETENTION_LIMIT"
    )
    ws_rate_limit_window_seconds: int = Field(
        default=60, ge=1, alias="WS_RATE_LIMIT_WINDOW_SECONDS"
    )
    ws_rate_limit_max_messages: int = Field(
        default=20, ge=1, alias="WS_RATE_LIMIT_MAX_MESSAGES"
    )
    database_url: str = Field(default="sqlite:///./yuzuki-ai.db", alias="DATABASE_URL")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore
