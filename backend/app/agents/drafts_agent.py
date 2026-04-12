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

## Output Format
Write the draft communication, then on a new line provide a JSON summary:
{"draft_type": "email|letter|complaint|memo|question", "title": "Subject/title", "recipient": "Who this goes to", "tone": "professional|firm|conciliatory"}
"""

    messages = [
        SystemMessage(content=system_content),
        HumanMessage(content=f"Drafting task: {delegation_task}"),
    ]

    response = await llm.ainvoke(messages)
    response_text = response.content

    # Parse the draft metadata
    draft_meta = {
        "type": "email",
        "title": "Draft Communication",
        "content": response_text,
        "recipient": None,
        "tone": "professional",
    }

    lines = response_text.strip().split("\n")
    for line in reversed(lines):
        line = line.strip()
        if line.startswith('{"draft_type"'):
            try:
                parsed = json.loads(line)
                draft_meta["type"] = parsed.get("draft_type", "email")
                draft_meta["title"] = parsed.get("title", "Draft Communication")
                draft_meta["recipient"] = parsed.get("recipient")
                draft_meta["tone"] = parsed.get("tone", "professional")
                # Remove the JSON line from the content
                draft_meta["content"] = "\n".join(lines[:-1]).strip()
                break
            except json.JSONDecodeError:
                pass

    updates = {
        "current_agent": "navigator",
        "drafts_generated": [draft_meta],
        "messages": [
            AIMessage(
                content=f"[Draft Studio]\n\n{draft_meta['content']}",
                name="drafts",
            )
        ],
    }

    return Command(goto="navigator_agent", update=updates)
