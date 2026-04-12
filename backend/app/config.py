"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite+aiosqlite:///./data/clubresolve.db"

    # JWT Auth
    jwt_secret_key: str = "change-me-to-a-random-secret"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 1440  # 24 hours

    # Encryption for BYOK API keys
    clubresolve_encryption_key: str = "change-me-generate-with-fernet"

    # ChromaDB
    chroma_persist_dir: str = "./data/chroma_db"

    # File uploads
    upload_dir: str = "./data/uploads"

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
