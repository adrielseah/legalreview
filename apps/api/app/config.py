from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env from apps/api so ISAACUS_API_KEY etc. are found regardless of cwd
_env_path = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_env_path, extra="ignore")

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

    # Isaacus — legal embedding (kanon-2-embedder). When set, used for clause/precedent embeddings (backfill + new clauses).
    # Leave blank to use Gemini/OpenAI. See https://docs.isaacus.com/capabilities/embedding
    isaacus_api_key: str = ""
    isaacus_embedding_model: str = "kanon-2-embedder"
    # Isaacus supports 1792, 1536, 1024, 768, 512, 256.
    # Default to 1536 to match existing Supabase vector(1536) columns.
    isaacus_embedding_dim: int = 1536
    # Dimension of embedding columns in DB (embedding_cache, precedent_clauses, clauses).
    # Must match schema; used when normalizing API results before insert so DB never sees wrong size.
    embedding_schema_dim: int = 1536

    # Model names — defaults are Gemini free-tier models
    explanation_model: str = "gemini-2.5-flash-lite"
    doctype_model: str = "gemini-2.5-flash-lite"
    embedding_model: str = "text-embedding-004"
    embedding_dim: int = 768

    # Upload limits
    max_upload_bytes: int = 26_214_400  # 25 MB

    # Feature flags — set DISABLE_EMBEDDINGS=true to turn off clause/precedent embeddings
    disable_llm: bool = False
    disable_ocr: bool = False
    disable_embeddings: bool = False
    enable_ocr_evidence: bool = False
    ocr_alpha_ratio_threshold: float = 0.3

    # Storage bucket names
    bucket_raw: str = "contracts-raw"
    bucket_derived: str = "contracts-derived"

    # App — CORS allowed origins. Set CORS_ORIGINS env (JSON array) to override.
    cors_origins: list = [
        "http://localhost:3000",
        "http://localhost:3001",
        "https://legalreview-web.vercel.app",
    ]
    # Set ADMIN_API_KEY to a long random secret in production
    admin_api_key: str = ""

    # Auth — OTP-based login
    jwt_secret: str = "change-me-in-production"
    jwt_expiry_hours: int = 24
    otp_expiry_minutes: int = 15
    otp_max_attempts: int = 5
    allowed_email_domains: list = ["@open.gov.sg", "@tech.gov.sg"]
    postman_api_key: str = ""
    email_from_name: str = "ClauseLens"


@lru_cache
def get_settings() -> Settings:
    return Settings()
