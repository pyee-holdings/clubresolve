"""LiteLLM-backed model routing for BYOK.

Supports per-task model routing:
- fast: cheap model for intake extraction, classification, basic drafting
- strong: powerful model for strategy synthesis, legal analysis
- long: long-context model for document review, evidence consolidation
"""

import litellm
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel

from app.services.crypto import decrypt_api_key

# Default models per provider per tier
DEFAULT_MODELS = {
    "anthropic": {
        "fast": "claude-haiku-4-20250414",
        "strong": "claude-sonnet-4-20250514",
        "long": "claude-sonnet-4-20250514",
    },
    "openai": {
        "fast": "gpt-4o-mini",
        "strong": "gpt-4o",
        "long": "gpt-4o",
    },
    "google": {
        "fast": "gemini-2.0-flash",
        "strong": "gemini-2.5-pro",
        "long": "gemini-2.5-pro",
    },
}


def get_litellm_model_name(provider: str, model: str) -> str:
    """Convert provider + model to LiteLLM format."""
    prefixes = {
        "anthropic": "",  # LiteLLM uses raw model names for Anthropic
        "openai": "",
        "google": "gemini/",
    }
    prefix = prefixes.get(provider, "")
    return f"{prefix}{model}" if prefix else model


def create_chat_model(
    provider: str,
    encrypted_key: bytes,
    model_tier: str = "strong",
    preferred_model: str | None = None,
) -> BaseChatModel:
    """Create a LangChain chat model from BYOK credentials.

    Args:
        provider: LLM provider ("anthropic", "openai", "google")
        encrypted_key: Fernet-encrypted API key
        model_tier: "fast", "strong", or "long"
        preferred_model: Override model name (optional)

    Returns:
        LangChain BaseChatModel ready for use
    """
    api_key = decrypt_api_key(encrypted_key)
    model_name = preferred_model or DEFAULT_MODELS.get(provider, {}).get(model_tier, "")

    if not model_name:
        raise ValueError(f"No default model for provider={provider}, tier={model_tier}")

    if provider == "anthropic":
        return ChatAnthropic(
            model=model_name,
            api_key=api_key,
            max_tokens=4096,
        )
    elif provider == "openai":
        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
        )
    else:
        # Fall back to LiteLLM for other providers
        litellm_model = get_litellm_model_name(provider, model_name)
        # Use LiteLLM's completion directly wrapped in a LangChain-compatible way
        return ChatOpenAI(
            model=litellm_model,
            api_key=api_key,
            base_url="https://litellm-proxy.example.com",  # Replace with actual proxy or use litellm directly
        )


async def validate_api_key(provider: str, api_key: str) -> bool:
    """Test an API key by making a minimal request.

    Returns True if the key works, False otherwise.
    """
    try:
        model = DEFAULT_MODELS.get(provider, {}).get("fast", "")
        if not model:
            return False

        litellm_model = get_litellm_model_name(provider, model)

        # Set the API key for the provider
        api_key_param = f"{provider.upper()}_API_KEY"

        response = await litellm.acompletion(
            model=litellm_model,
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=5,
            api_key=api_key,
        )
        return response is not None
    except Exception:
        return False
