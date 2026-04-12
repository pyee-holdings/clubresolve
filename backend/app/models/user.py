"""User and API key configuration models."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    api_keys: Mapped[list["APIKeyConfig"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    cases: Mapped[list["Case"]] = relationship(back_populates="user", cascade="all, delete-orphan")  # noqa: F821


class APIKeyConfig(Base):
    __tablename__ = "api_key_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # "anthropic", "openai", "google"
    encrypted_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    preferred_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_tier: Mapped[str] = mapped_column(String(20), default="strong")  # "fast", "strong", "long"
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="api_keys")
