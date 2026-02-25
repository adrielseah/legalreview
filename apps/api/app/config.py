from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://clauselens:clauselens@localhost:5432/clauselens"
    sync_database_url: str = "postgresql://clauselens:clauselens@localhost:5432/clauselens"

    # Supabase (prod)
    supabase_url: str = ""
    supabase_service_role_key: str = ""

    # Storage backend: "supabase" or "minio"
    storage_backend: str = "minio"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_secure: bool = False

    # AI provider — set GEMINI_API_KEY to use Gemini (free tier), otherwise OpenAI is used
    gemini_api_key: str = ""
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"

    # OpenAI (fallback if gemini_api_key is not set)
    openai_api_key: str = ""

    # Model names — defaults are Gemini free-tier models
    explanation_model: str = "gemini-2.5-flash-lite"
    doctype_model: str = "gemini-2.5-flash-lite"
    embedding_model: str = "text-embedding-004"
    embedding_dim: int = 768

    # Similarity
    similarity_threshold: float = 0.85

    # Upload limits
    max_upload_bytes: int = 26_214_400  # 25 MB

    # Feature flags
    disable_llm: bool = False
    disable_ocr: bool = False
    disable_embeddings: bool = False
    enable_ocr_evidence: bool = False
    ocr_alpha_ratio_threshold: float = 0.3

    # Storage bucket names
    bucket_raw: str = "contracts-raw"
    bucket_derived: str = "contracts-derived"

    # App — set CORS_ORIGINS env var in production, e.g. '["https://yourdomain.com"]'
    cors_origins: list = ["http://localhost:3000", "http://localhost:3001"]
    # Set ADMIN_API_KEY to a long random secret in production
    admin_api_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
