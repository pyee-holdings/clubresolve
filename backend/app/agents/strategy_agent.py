"""Navigator (Strategy Agent) — the supervisor node.

Uses LLM tool calling for reliable delegation instead of parsing JSON from text.
"""

import json
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.types import Command

from app.agents.state import CaseState
from app.agents.prompts.strategy import NAVIGATOR_SYSTEM_PROMPT


@tool
def delegate_to_counsel(task: str) -> str:
    """Delegate a research task to the Counsel agent for policy/governance analysis.

    Use this when you need to research BC laws, club bylaws, SafeSport policies,
    or any governance-related regulations relevant to the parent's case.

    Args:
        task: Specific research question, e.g. "Research what the BC Societies Act says about member rights to inspect financial records"
    """
    return f"Delegating to Counsel: {task}"


@tool
def delegate_to_vault(task: str) -> str:
    """Delegate an evidence organization task to the Vault agent.

    Use this when you need to organize evidence, build timelines, extract key facts
    from documents, identify contradictions, or prepare escalation-ready summaries.

    Args:
        task: Specific evidence task, e.g. "Organize the email chain into a timeline of events with key issues highlighted"
    """
    return f"Delegating to Vault: {task}"


@tool
def delegate_to_drafts(task: str) -> str:
    """Delegate a communication drafting task to the Draft Studio agent.

    Use this when you need to draft emails, letters, complaints, or other
    communications for the parent to send.

    Args:
        task: Specific drafting task, e.g. "Draft a polite inquiry email to the club treasurer requesting an itemized breakdown"
    """
    return f"Delegating to Draft Studio: {task}"


DELEGATION_TOOLS = [delegate_to_counsel, delegate_to_vault, delegate_to_drafts]

TOOL_TO_AGENT = {
    "delegate_to_counsel": "counsel_agent",
    "delegate_to_vault": "vault_agent",
    "delegate_to_drafts": "drafts_agent",
}


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

    if state.get("legal_findings"):
        findings_summary = "; ".join(
            f"{f.get('finding', '')} [{f.get('confidence', 'unknown')} confidence]"
            for f in state["legal_findings"][-3:]
        )
        parts.append(f"Recent Legal Findings: {findings_summary}")

    if state.get("evidence_summary"):
        parts.append(f"Evidence Summary: {state['evidence_summary']}")

    if state.get("missing_info"):
        parts.append(f"Still Missing: {', '.join(state['missing_info'])}")

    return "\n".join(parts)


async def navigator_node(state: CaseState, config) -> Command:
    """Navigator agent node — the supervisor/case manager.

    Uses tool calling for delegation. The LLM can either:
    1. Respond directly (no tool call) → end turn
    2. Call a delegation tool → route to specialist
    3. Respond AND call a tool → respond then route
    """
    llm = config["configurable"]["llm"]

    # Bind delegation tools to the LLM
    llm_with_tools = llm.bind_tools(DELEGATION_TOOLS)

    # Build the system message with case context
    context = _build_context_summary(state)
    system_content = NAVIGATOR_SYSTEM_PROMPT
    if context:
        system_content += f"\n\n## Current Case Context\n{context}"

    system_content += """

## Delegation Instructions
You have access to three delegation tools. Use them ONLY when the conditions below are clearly met:

- **delegate_to_vault**: Call this ONLY when the user has **provided actual evidence content** in the conversation — e.g., they pasted an email, shared specific dates/names/quotes, or described concrete events with verifiable details. Do NOT delegate if the user merely *mentions* having evidence (e.g., "I have an email from the coach"). Instead, ask them to share it: "Could you paste the email or share the key details so I can organize it?"

- **delegate_to_counsel**: Call this ONLY when a **specific policy or legal question** arises that you cannot answer from existing case context — e.g., "What does the BC Societies Act say about member rights to financial records?"

- **delegate_to_drafts**: Call this ONLY when the user **explicitly asks for a draft** AND you have enough specifics (who the recipient is, what the issue is, what tone). If the user says something vague like "I want to write a complaint," ask clarifying questions first: "Who would you like to send this to? What specific issue should it address?"

## When NOT to Delegate
- The user is still describing their situation or asking general questions — respond directly
- The user mentions evidence they have but hasn't shared it yet — ask them to provide it
- The user wants a draft but hasn't specified recipient/issue — ask clarifying questions
- You're providing an assessment, next steps, or general guidance — respond directly

When you identify next steps, include them in your response clearly numbered.
"""

    messages = [SystemMessage(content=system_content)] + list(state["messages"])

    response = await llm_with_tools.ainvoke(messages)

    # Check if the LLM made a tool call
    tool_calls = getattr(response, "tool_calls", None) or []

    updates = {"current_agent": "navigator"}

    # Extract text content (may be empty if only tool call)
    response_text = response.content or ""

    if tool_calls:
        # Get the first delegation tool call
        tc = tool_calls[0]
        tool_name = tc["name"]
        tool_args = tc["args"]

        if tool_name in TOOL_TO_AGENT:
            target_agent = TOOL_TO_AGENT[tool_name]
            task = tool_args.get("task", "")

            if response_text:
                updates["messages"] = [AIMessage(content=response_text)]

            updates["delegation_task"] = task

            return Command(
                goto=target_agent,
                update=updates,
            )

    # No delegation — direct response
    if response_text:
        updates["messages"] = [AIMessage(content=response_text)]

    return Command(
        goto="__end__",
        update=updates,
    )
