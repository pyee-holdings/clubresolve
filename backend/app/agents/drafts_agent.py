"""Draft Studio agent — communication drafting specialist.

Generates ready-to-use emails, letters, complaints, and other
communications that parents can send.
"""

import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.types import Command

from app.agents.state import CaseState
from app.agents.prompts.drafts import DRAFTS_SYSTEM_PROMPT


async def drafts_node(state: CaseState, config) -> Command:
    """Draft Studio agent node — generates communications.

    Called by Navigator with a specific drafting task.
    Returns generated draft back to Navigator.
    """
    llm = config["configurable"]["llm"]

    delegation_task = state.get("delegation_task", "")

    # Gather case context for the draft
    context_parts = []
    if state.get("club_name"):
        context_parts.append(f"Club: {state['club_name']}")
    if state.get("sport"):
        context_parts.append(f"Sport: {state['sport']}")
    if state.get("description"):
        context_parts.append(f"Issue: {state['description']}")
    if state.get("desired_outcome"):
        context_parts.append(f"Desired Outcome: {state['desired_outcome']}")
    if state.get("people_involved"):
        people = ", ".join(
            f"{p.get('name', '?')} ({p.get('role', '?')})"
            for p in state["people_involved"]
        )
        context_parts.append(f"People Involved: {people}")

    # Include legal findings for evidence-backed drafting
    if state.get("legal_findings"):
        findings = "; ".join(
            f"{f.get('finding', '')} (Source: {f.get('source', 'unknown')})"
            for f in state["legal_findings"][-5:]
        )
        context_parts.append(f"Relevant Policy Findings: {findings}")

    # Include evidence for reference
    if state.get("evidence_summary"):
        context_parts.append(f"Evidence Summary: {state['evidence_summary']}")

    case_context = "\n".join(context_parts)
    escalation_level = state.get("escalation_level", 0)

    system_content = DRAFTS_SYSTEM_PROMPT
    system_content += f"\n\n## Case Context\n{case_context}"
    system_content += f"\n\nCurrent escalation level: {escalation_level}"

    system_content += """

## Before Drafting
If the delegation task is vague or you lack key details (recipient, specific issue, desired tone), do NOT generate a speculative draft. Instead, respond with what information you still need. For example:
- "To draft this email, I need to know: (1) Who is the recipient? (2) What specific issue should it address?"

Only generate a draft when you have enough concrete details to write something useful and accurate.

## Output Format
When you DO have enough info to draft, write the communication, then on a new line provide a JSON summary:
{"draft_type": "email|letter|complaint|memo|question", "title": "Subject/title", "recipient": "Who this goes to", "tone": "professional|firm|conciliatory"}

If you are NOT drafting (because you need more info), just respond with your questions — do NOT include the JSON summary line.
"""

    messages = [
        SystemMessage(content=system_content),
        HumanMessage(content=f"Drafting task: {delegation_task}"),
    ]

    response = await llm.ainvoke(messages)
    response_text = response.content

    # Parse the draft metadata — only if the agent actually produced a draft
    draft_meta = None
    lines = response_text.strip().split("\n")
    for line in reversed(lines):
        line = line.strip()
        if line.startswith('{"draft_type"'):
            try:
                parsed = json.loads(line)
                draft_meta = {
                    "type": parsed.get("draft_type", "email"),
                    "title": parsed.get("title", "Draft Communication"),
                    "content": "\n".join(lines[:-1]).strip(),
                    "recipient": parsed.get("recipient"),
                    "tone": parsed.get("tone", "professional"),
                }
                break
            except json.JSONDecodeError:
                pass

    updates = {
        "current_agent": "navigator",
        "messages": [
            AIMessage(
                content=f"[Draft Studio]\n\n{draft_meta['content'] if draft_meta else response_text}",
                name="drafts",
            )
        ],
    }

    # Only store draft if one was actually generated (not just clarifying questions)
    if draft_meta:
        updates["drafts_generated"] = [draft_meta]

    return Command(goto="navigator_agent", update=updates)
