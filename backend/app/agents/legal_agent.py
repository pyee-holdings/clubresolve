"""Counsel (Legal Agent) — policy and governance research specialist.

Searches the knowledge base for relevant BC laws, policies, and regulations.
Returns findings with confidence levels and citations back to Navigator.
"""

import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.types import Command

from app.agents.state import CaseState
from app.agents.prompts.legal import COUNSEL_SYSTEM_PROMPT


async def counsel_node(state: CaseState, config) -> Command:
    """Counsel agent node — researches policies and regulations.

    Called by Navigator with a specific research task.
    Returns findings back to Navigator.
    """
    llm = config["configurable"]["llm"]
    retriever = config["configurable"].get("retriever")

    delegation_task = state.get("delegation_task", "")

    # Build context from case state
    context_parts = []
    if state.get("club_name"):
        context_parts.append(f"Club: {state['club_name']}")
    if state.get("sport"):
        context_parts.append(f"Sport: {state['sport']}")
    if state.get("case_category"):
        context_parts.append(f"Issue Category: {state['case_category']}")
    if state.get("description"):
        context_parts.append(f"Issue Description: {state['description']}")

    case_context = "\n".join(context_parts)

    # Retrieve relevant documents from knowledge base
    retrieved_context = ""
    if retriever and delegation_task:
        try:
            docs = await retriever.ainvoke(delegation_task)
            if docs:
                retrieved_context = "\n\n---\n\n".join(
                    f"**Source: {doc.metadata.get('source', 'Unknown')}**\n{doc.page_content}"
                    for doc in docs[:5]
                )
        except Exception:
            retrieved_context = "(Knowledge base search unavailable)"

    # Build the prompt
    system_content = COUNSEL_SYSTEM_PROMPT
    system_content += f"\n\n## Case Context\n{case_context}"

    if retrieved_context:
        system_content += f"\n\n## Retrieved Policy/Regulation Sources\n{retrieved_context}"
    else:
        system_content += "\n\n## Note: No specific policy documents were retrieved. Base your analysis on general knowledge of BC sports governance, but clearly note that specific documents should be reviewed."

    system_content += """

## Output Format
Respond with your research findings. Structure your response as:
1. Relevant policies/rules found (with source citations)
2. Rights and obligations that may apply
3. Factual gaps or assumptions
4. Evidence that would strengthen the position
5. Confidence level for each finding (HIGH/MEDIUM/LOW)

At the end, provide a JSON summary on its own line:
{"findings": [{"finding": "...", "source": "...", "confidence": "high|medium|low"}], "evidence_needed": ["..."], "summary": "..."}
"""

    messages = [
        SystemMessage(content=system_content),
        HumanMessage(content=f"Research task: {delegation_task}"),
    ]

    response = await llm.ainvoke(messages)
    response_text = response.content

    # Parse structured findings from the response
    findings = []
    legal_summary = response_text
    evidence_needed = []

    # Try to extract JSON summary
    lines = response_text.strip().split("\n")
    for line in reversed(lines):
        line = line.strip()
        if line.startswith('{"findings"'):
            try:
                parsed = json.loads(line)
                findings = parsed.get("findings", [])
                evidence_needed = parsed.get("evidence_needed", [])
                if parsed.get("summary"):
                    legal_summary = parsed["summary"]
                break
            except json.JSONDecodeError:
                pass

    # Build update and return to navigator
    updates = {
        "current_agent": "navigator",
        "legal_findings": findings,
        "legal_summary": legal_summary,
        "messages": [
            AIMessage(
                content=f"[Counsel Research Complete]\n\n{response_text}",
                name="counsel",
            )
        ],
    }

    if evidence_needed:
        current_missing = list(state.get("missing_info", []))
        updates["missing_info"] = list(set(current_missing + evidence_needed))

    return Command(goto="navigator_agent", update=updates)
