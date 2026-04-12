"""User and auth schemas."""

from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    email: EmailStr
    name: str
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    name: str

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class APIKeyCreate(BaseModel):
    provider: str  # "anthropic", "openai", "google"
    api_key: str
    preferred_model: str | None = None
    model_tier: str = "strong"  # "fast", "strong", "long"


class APIKeyResponse(BaseModel):
    id: str
    provider: str
    preferred_model: str | None
    model_tier: str
    is_active: bool

    model_config = {"from_attributes": True}
