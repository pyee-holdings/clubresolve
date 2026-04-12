"""Vault (Evidence Agent) — structured evidence management specialist.

Organizes evidence, builds timelines, identifies contradictions,
and generates escalation-ready documents.
"""

import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.types import Command

from app.agents.state import CaseState
from app.agents.prompts.evidence import VAULT_SYSTEM_PROMPT


async def vault_node(state: CaseState, config) -> Command:
    """Vault agent node — evidence organization and analysis.

    Called by Navigator with a specific evidence task.
    Returns organized evidence back to Navigator.
    """
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

    system_content += """

## Output Format
After your analysis, provide a JSON summary on its own line:
{"new_timeline_events": [{"event_date": "YYYY-MM-DD", "description": "..."}], "contradictions": ["..."], "unanswered_questions": ["..."], "evidence_summary": "..."}
"""

    messages = [
        SystemMessage(content=system_content),
        HumanMessage(content=f"Evidence task: {delegation_task}"),
    ]

    response = await llm.ainvoke(messages)
    response_text = response.content

    # Parse structured output
    new_events = []
    new_contradictions = []
    new_questions = []
    evidence_summary = None

    lines = response_text.strip().split("\n")
    for line in reversed(lines):
        line = line.strip()
        if line.startswith('{"new_timeline_events"') or line.startswith('{"contradictions"') or line.startswith('{"evidence_summary"'):
            try:
                parsed = json.loads(line)
                new_events = parsed.get("new_timeline_events", [])
                new_contradictions = parsed.get("contradictions", [])
                new_questions = parsed.get("unanswered_questions", [])
                evidence_summary = parsed.get("evidence_summary")
                break
            except json.JSONDecodeError:
                pass

    updates = {
        "current_agent": "navigator",
        "messages": [
            AIMessage(
                content=f"[Vault Analysis Complete]\n\n{response_text}",
                name="vault",
            )
        ],
    }

    if new_events:
        updates["timeline_events"] = new_events
    if new_contradictions:
        updates["contradictions"] = new_contradictions
    if new_questions:
        updates["unanswered_questions"] = new_questions
    if evidence_summary:
        updates["evidence_summary"] = evidence_summary

    return Command(goto="navigator_agent", update=updates)
