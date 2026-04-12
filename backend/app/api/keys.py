"""BYOK API key management endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User, APIKeyConfig
from app.api.auth import get_current_user
from app.schemas.user import APIKeyCreate, APIKeyResponse
from app.services.crypto import encrypt_api_key
from app.services.llm_router import validate_api_key

router = APIRouter(prefix="/api/keys", tags=["keys"])


@router.post("", response_model=APIKeyResponse)
async def save_api_key(
    key_data: APIKeyCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save an encrypted API key for a provider."""
    # Check if key already exists for this provider
    result = await db.execute(
        select(APIKeyConfig).where(
            APIKeyConfig.user_id == current_user.id,
            APIKeyConfig.provider == key_data.provider,
        )
    )
    existing = result.scalar_one_or_none()

    encrypted = encrypt_api_key(key_data.api_key)

    if existing:
        existing.encrypted_key = encrypted
        existing.preferred_model = key_data.preferred_model
        existing.model_tier = key_data.model_tier
        existing.is_active = True
        await db.flush()
        return existing

    config = APIKeyConfig(
        user_id=current_user.id,
        provider=key_data.provider,
        encrypted_key=encrypted,
        preferred_model=key_data.preferred_model,
        model_tier=key_data.model_tier,
    )
    db.add(config)
    await db.flush()
    return config


@router.get("", response_model=list[APIKeyResponse])
async def list_api_keys(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List configured providers (no key values returned)."""
    result = await db.execute(
        select(APIKeyConfig).where(APIKeyConfig.user_id == current_user.id)
    )
    return result.scalars().all()


@router.delete("/{provider}")
async def delete_api_key(
    provider: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove an API key for a provider."""
    result = await db.execute(
        select(APIKeyConfig).where(
            APIKeyConfig.user_id == current_user.id,
            APIKeyConfig.provider == provider,
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="API key not found for this provider")

    await db.delete(config)
    return {"detail": "API key removed"}


@router.post("/validate")
async def validate_key(key_data: APIKeyCreate):
    """Test an API key before saving."""
    is_valid = await validate_api_key(key_data.provider, key_data.api_key)
    return {"valid": is_valid, "provider": key_data.provider}
