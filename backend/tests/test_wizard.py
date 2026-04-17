"""Tests for the Wizard action plan service and API route."""

import json
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

import pytest

from app.services.action_plan import (
    load_knowledge_base,
    build_prompt,
    generate_action_plan,
    DISCLAIMER,
    _knowledge_base_cache,
)


# ── Service Tests ─────────────────────────────────────────


class TestLoadKnowledgeBase:
    def setup_method(self):
        """Reset cache before each test."""
        import app.services.action_plan as ap
        ap._knowledge_base_cache = None

    def test_loads_all_markdown_files(self):
        """Knowledge base loads all 4 source files."""
        kb = load_knowledge_base()
        assert len(kb) > 0
        assert "BC Societies Act" in kb
        assert "SafeSport" in kb or "safesport" in kb.lower()
        assert "Escalation" in kb or "escalation" in kb.lower()

    def test_caches_after_first_load(self):
        """Knowledge base is cached after first load."""
        kb1 = load_knowledge_base()
        kb2 = load_knowledge_base()
        assert kb1 is kb2  # Same object reference (cached)

    def test_raises_if_directory_missing(self, tmp_path):
        """Raises FileNotFoundError if knowledge directory doesn't exist."""
        import app.services.action_plan as ap
        original_dir = ap.KNOWLEDGE_DIR
        ap.KNOWLEDGE_DIR = tmp_path / "nonexistent"
        ap._knowledge_base_cache = None
        try:
            with pytest.raises(FileNotFoundError):
                load_knowledge_base()
        finally:
            ap.KNOWLEDGE_DIR = original_dir
            ap._knowledge_base_cache = None


class TestBuildPrompt:
    def test_returns_system_and_user_prompts(self):
        """build_prompt returns a tuple of (system_prompt, user_prompt)."""
        intake = {
            "province": "BC",
            "sport": "Soccer",
            "category": "governance",
            "tried": "verbal",
            "desired_outcome": "accountability",
            "description": "The board changed the rules without a vote.",
        }
        system, user = build_prompt(intake)
        assert isinstance(system, str)
        assert isinstance(user, str)

    def test_system_prompt_contains_knowledge_base(self):
        """System prompt includes the knowledge base content."""
        intake = {"province": "BC", "sport": "Hockey", "category": "billing"}
        system, _ = build_prompt(intake)
        assert "BC Societies Act" in system

    def test_user_prompt_contains_intake_data(self):
        """User prompt includes all intake fields."""
        intake = {
            "province": "BC",
            "sport": "Soccer",
            "category": "governance",
            "tried": "wrote a complaint",
            "desired_outcome": "reverse the decision",
            "description": "Board expelled my child without a hearing.",
        }
        _, user = build_prompt(intake)
        assert "Soccer" in user
        assert "governance" in user
        assert "Board expelled my child" in user

    def test_handles_missing_optional_fields(self):
        """Build prompt works with minimal intake data."""
        intake = {"province": "BC", "sport": "Hockey", "category": "billing"}
        system, user = build_prompt(intake)
        assert "Hockey" in user
        assert "billing" in user


class TestGenerateActionPlan:
    @pytest.mark.asyncio
    async def test_happy_path_returns_valid_plan(self):
        """Returns a valid action plan when LLM responds correctly."""
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps(
                        {
                            "summary": "This is a governance issue.",
                            "steps": [
                                {
                                    "title": "Request records",
                                    "description": "Ask for meeting minutes.",
                                    "citation": "BC Societies Act, s. 20(1)",
                                    "template": "Dear President...",
                                    "deadline": "Send within 3 days",
                                }
                            ],
                            "escalation_timeline": [
                                {
                                    "if": "No response in 14 days",
                                    "then": "Escalate to PSO",
                                    "deadline": "Day 15",
                                }
                            ],
                            "disclaimer": DISCLAIMER,
                        }
                    )
                )
            )
        ]

        with patch("app.services.action_plan.litellm.acompletion", new_callable=AsyncMock) as mock_llm, \
             patch("app.services.action_plan.decrypt_api_key", return_value="test-key"):
            mock_llm.return_value = mock_response

            plan = await generate_action_plan(
                intake_data={"province": "BC", "sport": "Soccer", "category": "governance"},
                provider="anthropic",
                encrypted_key=b"encrypted",
            )

        assert plan["summary"] == "This is a governance issue."
        assert len(plan["steps"]) == 1
        assert plan["steps"][0]["title"] == "Request records"
        assert len(plan["escalation_timeline"]) == 1

    @pytest.mark.asyncio
    async def test_timeout_raises_error(self):
        """Raises TimeoutError when LLM takes too long."""
        async def slow_response(*args, **kwargs):
            await asyncio.sleep(60)

        with patch("app.services.action_plan.litellm.acompletion", side_effect=slow_response), \
             patch("app.services.action_plan.decrypt_api_key", return_value="test-key"), \
             patch("app.services.action_plan.asyncio.wait_for", side_effect=asyncio.TimeoutError):
            with pytest.raises(TimeoutError, match="timed out"):
                await generate_action_plan(
                    intake_data={"province": "BC", "sport": "Soccer", "category": "governance"},
                    provider="anthropic",
                    encrypted_key=b"encrypted",
                )

    @pytest.mark.asyncio
    async def test_malformed_json_raises_error(self):
        """Raises ValueError when LLM returns invalid JSON."""
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="This is not JSON at all"))
        ]

        with patch("app.services.action_plan.litellm.acompletion", new_callable=AsyncMock) as mock_llm, \
             patch("app.services.action_plan.decrypt_api_key", return_value="test-key"):
            mock_llm.return_value = mock_response

            with pytest.raises(ValueError, match="invalid JSON"):
                await generate_action_plan(
                    intake_data={"province": "BC", "sport": "Soccer", "category": "governance"},
                    provider="anthropic",
                    encrypted_key=b"encrypted",
                )

    @pytest.mark.asyncio
    async def test_adds_disclaimer_if_missing(self):
        """Adds default disclaimer if LLM response doesn't include one."""
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps(
                        {
                            "summary": "Test summary",
                            "steps": [],
                            "escalation_timeline": [],
                        }
                    )
                )
            )
        ]

        with patch("app.services.action_plan.litellm.acompletion", new_callable=AsyncMock) as mock_llm, \
             patch("app.services.action_plan.decrypt_api_key", return_value="test-key"):
            mock_llm.return_value = mock_response

            plan = await generate_action_plan(
                intake_data={"province": "BC", "sport": "Soccer", "category": "governance"},
                provider="anthropic",
                encrypted_key=b"encrypted",
            )

        assert plan["disclaimer"] == DISCLAIMER

    @pytest.mark.asyncio
    async def test_invalid_provider_raises_error(self):
        """Raises ValueError for unknown provider."""
        with patch("app.services.action_plan.decrypt_api_key", return_value="test-key"):
            with pytest.raises(ValueError, match="No default model"):
                await generate_action_plan(
                    intake_data={"province": "BC", "sport": "Soccer", "category": "governance"},
                    provider="nonexistent",
                    encrypted_key=b"encrypted",
                )
