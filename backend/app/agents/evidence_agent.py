"""Vault (Evidence Agent) — structured evidence management specialist.

Organizes evidence, builds timelines, identifies contradictions,
and generates escalation-ready documents.
"""

import json
import re

from dateutil import parser as dateutil_parser
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.types import Command

from app.agents.state import CaseState
from app.agents.prompts.evidence import VAULT_SYSTEM_PROMPT


def _normalize_date(raw: str | None) -> str | None:
    """Try to parse a free-form date string into YYYY-MM-DD.

    Returns None if the input is empty, clearly not a date, or unparseable.
    """
    if not raw or not isinstance(raw, str):
        return None
    raw = raw.strip()
    if not raw or raw.lower() in ("unknown", "n/a", "none", "null", "?"):
        return None
    try:
        dt = dateutil_parser.parse(raw, fuzzy=True)
        return dt.strftime("%Y-%m-%d")
    except (ValueError, OverflowError):
        return None


def _extract_json_from_text(text: str) -> dict | None:
    """Try to extract a JSON object from LLM response text.

    Handles JSON in code blocks, on its own line, or embedded in text.
    """
    # Try code blocks first: ```json ... ``` or ``` ... ```
    code_block = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if code_block:
        try:
            return json.loads(code_block.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find a JSON object on its own line
    for line in reversed(text.strip().split("\n")):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                pass

    # Try to find any JSON object in the text
    match = re.search(r'\{[^{}]*"(?:new_timeline_events|evidence_items|evidence_summary|contradictions)"[^{}]*\}', text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return None


async def vault_node(state: CaseState, config) -> Command:
    """Vault agent node — evidence organization and analysis."""
    llm = config["configurable"]["llm"]
    delegation_task = state.get("delegation_task", "")

    # Gather existing evidence context
    evidence_context = ""
    if state.get("evidence_items"):
        items = state["evidence_items"]
        evidence_context = "\n".join(
            f"- [{item.get('type', 'unknown')}] {item.get('title', 'Untitled')} "
            f"(Date: {item.get('event_date', 'unknown')}) — {item.get('description', '')}"
            for item in items
        )

    timeline_context = ""
    if state.get("timeline_events"):
        events = sorted(state["timeline_events"], key=lambda e: e.get("event_date", ""))
        timeline_context = "\n".join(
            f"- {event.get('event_date', '?')}: {event.get('description', '')}"
            for event in events
        )

    existing_contradictions = state.get("contradictions", [])
    existing_questions = state.get("unanswered_questions", [])

    # Build the prompt
    system_content = VAULT_SYSTEM_PROMPT

    if evidence_context:
        system_content += f"\n\n## Current Evidence Inventory\n{evidence_context}"
    if timeline_context:
        system_content += f"\n\n## Current Timeline\n{timeline_context}"
    if existing_contradictions:
        system_content += f"\n\n## Known Contradictions\n" + "\n".join(f"- {c}" for c in existing_contradictions)
    if existing_questions:
        system_content += f"\n\n## Unanswered Questions\n" + "\n".join(f"- {q}" for q in existing_questions)

    # Get the full conversation context (last few messages with actual content)
    conversation_context = ""
    for msg in state.get("messages", [])[-6:]:
        if hasattr(msg, "content") and msg.content:
            role = getattr(msg, "type", "unknown")
            content_preview = msg.content[:2000] if len(msg.content) > 2000 else msg.content
            conversation_context += f"\n[{role}]: {content_preview}\n"

    system_content += """

## CRITICAL: Evidence Standards
Only create evidence items for information the user has **directly provided** with concrete details — actual email text, specific dates, named individuals, quoted statements, or document contents shared in the conversation.

**Do NOT create evidence items from:**
- Vague mentions ("I have an email from the coach" — this is not evidence until the user shares it)
- Your own inferences or assumptions about what happened
- General descriptions without specific dates, names, or content

If the user mentions evidence they haven't shared, add it to `unanswered_questions` (e.g., "User mentioned an email from the coach — content not yet provided").

Every evidence item MUST have a `source_reference` that points to what the user actually said or provided. If you cannot cite the user's actual words, do not create the item.

## Output Format
After your analysis, output a JSON block:

```json
{
  "evidence_items": [
    {"title": "...", "type": "email|document|receipt|note|correspondence|policy", "description": "...", "source_reference": "User provided email text: [quote first few words]", "event_date": "YYYY-MM-DD", "content": "key excerpt or summary", "tags": ["billing", "governance"]}
  ],
  "new_timeline_events": [
    {"event_date": "YYYY-MM-DD", "description": "...", "source": "...", "event_type": "incident|communication|deadline|action"}
  ],
  "contradictions": ["..."],
  "unanswered_questions": ["..."],
  "evidence_summary": "One paragraph summary of all evidence and its implications"
}
```

It is completely fine to return empty arrays if no concrete evidence was provided. Quality over quantity — only real, source-backed evidence items.
"""

    messages = [
        SystemMessage(content=system_content),
        HumanMessage(content=f"Evidence task: {delegation_task}\n\n## Conversation context:\n{conversation_context}"),
    ]

    response = await llm.ainvoke(messages)
    response_text = response.content

    # Parse structured output
    parsed = _extract_json_from_text(response_text)

    new_evidence = []
    new_events = []
    new_contradictions = []
    new_questions = []
    evidence_summary = None

    if parsed:
        new_evidence = parsed.get("evidence_items", [])
        new_events = parsed.get("new_timeline_events", [])
        new_contradictions = parsed.get("contradictions", [])
        new_questions = parsed.get("unanswered_questions", [])
        evidence_summary = parsed.get("evidence_summary")

        # Normalize dates to YYYY-MM-DD
        for item in new_evidence:
            item["event_date"] = _normalize_date(item.get("event_date"))
        for event in new_events:
            event["event_date"] = _normalize_date(event.get("event_date")) or "unknown"

    updates = {
        "current_agent": "navigator",
        "messages": [
            AIMessage(
                content=f"[Vault Analysis Complete]\n\n{response_text}",
                name="vault",
            )
        ],
    }

    if new_evidence:
        updates["evidence_items"] = new_evidence
    if new_events:
        updates["timeline_events"] = new_events
    if new_contradictions:
        updates["contradictions"] = new_contradictions
    if new_questions:
        updates["unanswered_questions"] = new_questions
    if evidence_summary:
        updates["evidence_summary"] = evidence_summary

    return Command(goto="navigator_agent", update=updates)
