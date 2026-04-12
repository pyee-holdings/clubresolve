"""Encryption service for BYOK API keys."""

from cryptography.fernet import Fernet

from app.config import settings

# Initialize Fernet with the server master key
_fernet = Fernet(settings.clubresolve_encryption_key.encode())


def encrypt_api_key(api_key: str) -> bytes:
    """Encrypt an API key for storage."""
    return _fernet.encrypt(api_key.encode())


def decrypt_api_key(encrypted_key: bytes) -> str:
    """Decrypt an API key for use in LLM calls."""
    return _fernet.decrypt(encrypted_key).decode()
