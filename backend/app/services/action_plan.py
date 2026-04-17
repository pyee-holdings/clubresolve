"""Action plan generation service for the Wizard.

Loads BC legislation knowledge base, builds a prompt, calls the LLM,
and returns a structured action plan with legal citations and template emails.
"""

import json
import asyncio
from pathlib import Path

import litellm

from app.services.crypto import decrypt_api_key
from app.services.llm_router import DEFAULT_MODELS, get_litellm_model_name

# Cache knowledge base at module level — loaded once on first call
_knowledge_base_cache: str | None = None

KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge" / "sources"

DISCLAIMER = (
    "ClubResolve provides advocacy support and general information about your rights "
    "as a member of a BC registered society. This is NOT legal advice. ClubResolve is "
    "not a law firm and does not replace consultation with a qualified lawyer. The "
    "information and templates provided are for educational and self-advocacy purposes "
    "only. Laws and bylaws vary — verify all citations against current legislation "
    "before taking action."
)

SYSTEM_PROMPT_TEMPLATE = """You are an advocacy support assistant helping parents navigate disputes with youth sports clubs in British Columbia, Canada. You are NOT a lawyer and must never claim to provide legal advice.

Your role is to:
1. Understand the parent's situation based on their intake responses
2. Identify relevant legal rights, governance rules, and escalation paths
3. Provide a concrete, step-by-step action plan with specific legal citations
4. Draft template emails/letters the parent can customize and send
5. Suggest an escalation timeline if initial steps don't resolve the issue

IMPORTANT RULES:
- Only cite sections and provisions that exist in the knowledge base below. If you are unsure of a citation, say "consult the full BC Societies Act for details" instead of guessing.
- Always include the disclaimer in your response.
- Be specific and actionable — the parent should know exactly what to do next.
- Reference specific bylaw provisions, Act sections, and organizational policies.
- Draft template letters should be professional, specific, and reference relevant legal provisions.

KNOWLEDGE BASE:
{knowledge_base}

You must respond with valid JSON matching this exact schema:
{{
  "summary": "1-2 sentence assessment of the situation and recommended approach",
  "steps": [
    {{
      "title": "Short title for this step",
      "description": "Detailed description of what to do and why",
      "citation": "Specific legal reference (e.g. 'BC Societies Act, s. 20(1)')",
      "template": "Draft email or letter text the parent can use",
      "deadline": "Suggested timeframe (e.g. '14 days from sending')"
    }}
  ],
  "escalation_timeline": [
    {{
      "if": "Condition (e.g. 'No response within 14 days')",
      "then": "Next action to take",
      "deadline": "Timeframe for this escalation step"
    }}
  ],
  "disclaimer": "{disclaimer}"
}}

Provide 3-5 action steps and 2-3 escalation steps. Each step should have a template email/letter where applicable.

EXAMPLE OUTPUT:
{{
  "summary": "This appears to be a governance violation where the board made a decision without following proper process. You have clear rights under the BC Societies Act to challenge this.",
  "steps": [
    {{
      "title": "Request club records",
      "description": "As a member of a BC registered society, you have the legal right to inspect the society's records, including meeting minutes, financial statements, and the member register. Submit a written request to the club secretary.",
      "citation": "BC Societies Act, s. 20(1) — Members' right to inspect records",
      "template": "Dear [Club Secretary],\\n\\nPursuant to Section 20(1) of the BC Societies Act (SBC 2015, c. 18), I am writing to request access to the following records of [Club Name]:\\n\\n1. Minutes of all board meetings held in [relevant period]\\n2. Current financial statements\\n3. Current register of members\\n\\nPlease provide copies within 14 days as required by the Act. I understand a reasonable copying fee may apply.\\n\\nThank you,\\n[Your Name]\\n[Membership Number]",
      "deadline": "Send within 3 days"
    }}
  ],
  "escalation_timeline": [
    {{
      "if": "No response to records request within 14 days",
      "then": "Send a follow-up letter referencing the original request and noting the society's obligation under s. 20. Copy the club president.",
      "deadline": "Day 15"
    }},
    {{
      "if": "Club refuses access to records",
      "then": "File a complaint with the BC Registrar of Societies (www.gov.bc.ca/societies) citing non-compliance with s. 20.",
      "deadline": "Within 7 days of refusal"
    }}
  ],
  "disclaimer": "{disclaimer}"
}}
"""


def load_knowledge_base() -> str:
    """Load all knowledge base markdown files and return as a single string."""
    global _knowledge_base_cache
    if _knowledge_base_cache is not None:
        return _knowledge_base_cache

    if not KNOWLEDGE_DIR.exists():
        raise FileNotFoundError(f"Knowledge base directory not found: {KNOWLEDGE_DIR}")

    parts = []
    for md_file in sorted(KNOWLEDGE_DIR.glob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        parts.append(content)

    if not parts:
        raise FileNotFoundError(f"No markdown files found in {KNOWLEDGE_DIR}")

    _knowledge_base_cache = "\n\n---\n\n".join(parts)
    return _knowledge_base_cache


def build_prompt(intake_data: dict) -> tuple[str, str]:
    """Build system and user prompts from intake data.

    Returns:
        Tuple of (system_prompt, user_prompt)
    """
    knowledge_base = load_knowledge_base()
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        knowledge_base=knowledge_base,
        disclaimer=DISCLAIMER,
    )

    user_prompt = f"""A parent in {intake_data.get('province', 'BC')} has submitted the following information about their sports club dispute:

Sport/Club Type: {intake_data.get('sport', 'Not specified')}
Dispute Category: {intake_data.get('category', 'Not specified')}
What They've Already Tried: {intake_data.get('tried', 'Nothing yet')}
Desired Outcome: {intake_data.get('desired_outcome', 'Not specified')}
Description: {intake_data.get('description', 'No additional details provided')}

Generate a personalized action plan for this parent. Remember to:
- Reference specific provisions from the knowledge base
- Draft template emails/letters they can customize
- Suggest realistic timelines
- Include escalation steps if initial actions don't work

Respond with valid JSON only, no markdown formatting."""

    return system_prompt, user_prompt


async def generate_action_plan(
    intake_data: dict,
    provider: str,
    encrypted_key: bytes,
    preferred_model: str | None = None,
) -> dict:
    """Generate an action plan using the LLM.

    Args:
        intake_data: Dict with intake form fields
        provider: LLM provider name
        encrypted_key: Encrypted BYOK API key
        preferred_model: Optional model override

    Returns:
        Parsed action plan dict matching ActionPlanResponse schema

    Raises:
        TimeoutError: If LLM call exceeds 45 seconds
        ValueError: If LLM returns invalid JSON
    """
    api_key = decrypt_api_key(encrypted_key)
    model_name = preferred_model or DEFAULT_MODELS.get(provider, {}).get("strong", "")

    if not model_name:
        raise ValueError(f"No default model for provider={provider}")

    litellm_model = get_litellm_model_name(provider, model_name)
    system_prompt, user_prompt = build_prompt(intake_data)

    try:
        response = await asyncio.wait_for(
            litellm.acompletion(
                model=litellm_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=4096,
                temperature=0.3,
                api_key=api_key,
                response_format={"type": "json_object"},
            ),
            timeout=45.0,
        )
    except asyncio.TimeoutError:
        raise TimeoutError("Action plan generation timed out after 45 seconds")

    content = response.choices[0].message.content

    try:
        plan = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM returned invalid JSON: {e}")

    # Ensure disclaimer is present
    if "disclaimer" not in plan or not plan["disclaimer"]:
        plan["disclaimer"] = DISCLAIMER

    return plan
