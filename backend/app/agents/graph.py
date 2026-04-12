"""LangGraph StateGraph — wires together all four agents.

Architecture:
- Navigator (strategy_agent) is the supervisor/hub
- Counsel, Vault, and Draft Studio are specialists
- All specialists return to Navigator via Command
- Navigator decides when to end (respond to user) or delegate further

            START
              |
              v
        +-----------+
        | Navigator |<---------+
        +-----------+          |
         /    |    \           |
        v     v     v          |
    Counsel Vault  Drafts      |
        \     |    /           |
         +----+---+------------+
          (Command -> navigator)
"""

from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from app.agents.state import CaseState
from app.agents.strategy_agent import navigator_node
from app.agents.legal_agent import counsel_node
from app.agents.evidence_agent import vault_node
from app.agents.drafts_agent import drafts_node


def build_case_graph():
    """Build the compiled LangGraph StateGraph.

    Returns a compiled graph ready for invocation.
    """
    graph = StateGraph(CaseState)

    # Add all agent nodes
    graph.add_node("navigator_agent", navigator_node)
    graph.add_node("counsel_agent", counsel_node)
    graph.add_node("vault_agent", vault_node)
    graph.add_node("drafts_agent", drafts_node)

    # Entry point: always start at Navigator
    graph.add_edge(START, "navigator_agent")

    # Note: routing is handled by Command returns from each node,
    # so no explicit conditional edges are needed. Each specialist
    # returns Command(goto="navigator_agent") and Navigator returns
    # Command(goto="__end__") or Command(goto="<specialist>").

    # Compile with in-memory checkpointer (swap for PostgresSaver in production)
    checkpointer = MemorySaver()

    return graph.compile(checkpointer=checkpointer)


# Module-level singleton graph instance
_graph = None


def get_graph():
    """Get or create the singleton graph instance."""
    global _graph
    if _graph is None:
        _graph = build_case_graph()
    return _graph


async def invoke_graph(
    llm,
    case,
    user_message: str,
    thread_id: str,
    retriever=None,
) -> dict:
    """Invoke the agent graph with a user message.

    Args:
        llm: LangChain chat model (from BYOK)
        case: Case SQLAlchemy model with structured intake data
        user_message: The user's chat message
        thread_id: LangGraph thread ID for checkpointing
        retriever: Optional knowledge base retriever for Counsel

    Returns:
        dict with response text, agent name, and any structured outputs
    """
    graph = get_graph()

    # Build input state from case data
    input_state = {
        "messages": [HumanMessage(content=user_message)],
        "case_id": case.id,
        "case_category": case.category,
        "club_name": case.club_name,
        "sport": case.sport,
        "description": case.description,
        "desired_outcome": case.desired_outcome,
        "urgency": case.urgency or "medium",
        "risk_flags": case.risk_flags or [],
        "people_involved": case.people_involved or [],
        "prior_attempts": case.prior_attempts,
        "intake_complete": case.status != "intake",
        "current_agent": "navigator",
        "delegation_task": None,
        "escalation_level": case.escalation_level or 0,
        # Initialize accumulator fields
        "legal_findings": [],
        "evidence_items": [],
        "timeline_events": [],
        "contradictions": [],
        "unanswered_questions": [],
        "drafts_generated": [],
    }

    config = {
        "configurable": {
            "thread_id": thread_id,
            "llm": llm,
            "retriever": retriever,
        }
    }

    # Invoke the graph
    result = await graph.ainvoke(input_state, config)

    # Extract the response from the last AI message
    response_text = ""
    agent_name = "navigator"

    for msg in reversed(result.get("messages", [])):
        if hasattr(msg, "content") and msg.type == "ai":
            response_text = msg.content
            agent_name = getattr(msg, "name", None) or "navigator"
            break

    return {
        "response": response_text,
        "agent": agent_name,
        "next_steps": result.get("next_steps"),
        "evidence_added": result.get("evidence_items"),
        "draft_generated": result.get("drafts_generated"),
        "legal_findings": result.get("legal_findings"),
        "metadata": {
            "escalation_level": result.get("escalation_level"),
            "confidence": result.get("confidence_level"),
            "missing_info": result.get("missing_info"),
        },
    }
