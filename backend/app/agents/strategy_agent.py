"""Navigator (Strategy Agent) — the supervisor node.

This is the hub of the entire system. Every user message enters here,
and every specialist returns results here. The Navigator decides:
- Whether to respond directly to the user
- Whether to delegate to Counsel (legal research)
- Whether to delegate to Vault (evidence organization)
- Whether to delegate to Draft Studio (communication drafting)
"""

import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.types import Command

from app.agents.state import CaseState
from app.agents.prompts.strategy import NAVIGATOR_SYSTEM_PROMPT


def _build_context_summary(state: CaseState) -> str:
    """Build a context summary from structured case state."""
    parts = []

    if state.get("club_name"):
        parts.append(f"Club: {state['club_name']}")
    if state.get("sport"):
        parts.append(f"Sport: {state['sport']}")
    if state.get("case_category"):
        parts.append(f"Category: {state['case_category']}")
    if state.get("urgency"):
        parts.append(f"Urgency: {state['urgency']}")
    if state.get("risk_flags"):
        parts.append(f"Risk Flags: {', '.join(state['risk_flags'])}")
    if state.get("desired_outcome"):
        parts.append(f"Desired Outcome: {state['desired_outcome']}")
    if state.get("prior_attempts"):
        parts.append(f"Prior Resolution Attempts: {state['prior_attempts']}")
    if state.get("description"):
        parts.append(f"Description: {state['description']}")

    # Include specialist findings if available
    if state.get("legal_findings"):
        findings_summary = "; ".join(
            f"{f.get('finding', '')} [{f.get('confidence', 'unknown')} confidence]"
            for f in state["legal_findings"][-3:]  # Last 3 findings
        )
        parts.append(f"Recent Legal Findings: {findings_summary}")

    if state.get("evidence_summary"):
        parts.append(f"Evidence Summary: {state['evidence_summary']}")

    if state.get("missing_info"):
        parts.append(f"Still Missing: {', '.join(state['missing_info'])}")

    return "\n".join(parts)


async def navigator_node(state: CaseState, config) -> Command:
    """Navigator agent node — the supervisor/case manager.

    Receives every user message and decides what to do next.
    Returns a Command that either responds to the user or delegates to a specialist.
    """
    llm = config["configurable"]["llm"]

    # Build the system message with case context
    context = _build_context_summary(state)
    system_content = NAVIGATOR_SYSTEM_PROMPT
    if context:
        system_content += f"\n\n## Current Case Context\n{context}"

    # Add instruction for structured decision-making
    system_content += """

## Decision Format
After analyzing the user's message, respond in this JSON format ONLY if you need to delegate:
{"delegate_to": "counsel|vault|drafts", "task": "specific task description"}

If you are responding directly to the user (most common), just respond naturally in plain text.
If you need to delegate AND respond, first write your response to the user, then on a new line write the JSON delegation.
"""

    messages = [SystemMessage(content=system_content)] + list(state["messages"])

    response = await llm.ainvoke(messages)
    response_text = response.content

    # Check if the response includes a delegation
    delegation = None
    user_response = response_text

    # Try to extract delegation JSON from the end of the response
    lines = response_text.strip().split("\n")
    for i, line in enumerate(lines):
        line = line.strip()
        if line.startswith('{"delegate_to"'):
            try:
                delegation = json.loads(line)
                user_response = "\n".join(lines[:i]).strip()
                break
            except json.JSONDecodeError:
                pass

    # Build state updates
    updates = {"current_agent": "navigator"}

    if delegation and delegation.get("delegate_to") in ("counsel", "vault", "drafts"):
        target = delegation["delegate_to"]
        task = delegation.get("task", "")

        agent_map = {
            "counsel": "counsel_agent",
            "vault": "vault_agent",
            "drafts": "drafts_agent",
        }

        # Add the user response as a message if there is one
        if user_response:
            updates["messages"] = [AIMessage(content=user_response)]

        updates["delegation_task"] = task

        # Add a message for the specialist
        return Command(
            goto=agent_map[target],
            update=updates,
        )

    # Direct response — no delegation
    updates["messages"] = [AIMessage(content=user_response)]
    return Command(
        goto="__end__",
        update=updates,
    )
