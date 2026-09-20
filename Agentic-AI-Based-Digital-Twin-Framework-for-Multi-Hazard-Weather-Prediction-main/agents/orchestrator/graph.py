"""
The Orchestrator's LangGraph state machine -- implements the "Workflow
Steps" from the architecture diagram:

    1. Receive user query          (entry point, see main.py)
    2. Understand intent (NLP)     -> understand_intent
    3. Break down into sub-tasks   -> plan_tasks
    4. Select & call tools/agents  -> call_tools
    5. Aggregate & validate        -> aggregate_and_validate
    6. Generate NL response        -> generate_response
    (7. Store memory / log)        -> finalize
"""

from __future__ import annotations

from typing import Any, Dict

from langgraph.graph import END, StateGraph

from .llm import llm_client
from .logging_config import get_logger
from .memory import conversation_memory
from .schemas import OrchestratorState
from .tools import call_tool

logger = get_logger(__name__)

_AVAILABLE_TOOLS_DESCRIPTION = """
- weather_tool: current/forecast weather data for a location (Agent 2)
- prediction_tool: ML rainfall/cloudburst/landslide predictions for a location (Agent 3)
- alert_tool: current alert/risk level for a location (Agent 4)
- trip_tool: mountain route planning, source/destination, itemized travel costs, way/corridor, and route hazards (Agent 15)
- digital_twin_tool: run a digital-twin simulation/query (Agent 5)
- report_tool: generate comprehensive disaster reports/summaries in PDF/JSON (Agent 6)
- data_tool: search historical datasets/records (Agent 7)
- rag_tool: search research papers/guidelines via RAG (Agent 8)
- notification_tool: send an email/SMS/push notification (Agent 9)
"""


def understand_intent(state: OrchestratorState) -> OrchestratorState:
    system = (
        "You are the intent-understanding module of a disaster-early-warning orchestrator agent. "
        "Given a user's query, respond with ONLY a JSON object (no prose, no markdown fences) of the form: "
        '{"intent": "<short intent label>", "entities": {"location": "...", "source": "...", "destination": "...", "timeframe": "...", "hazard_type": "..."}, '
        '"requires_tools": ["<tool_name>", ...]}. '
        "If the user asks about traveling, routes, costs, or going from A to B, include trip_tool, weather_tool, and alert_tool.\n"
        "If the user asks about flood risk, landslide risk, or multi-hazards, include alert_tool, digital_twin_tool, and weather_tool so hydrology and live risk are assessed together.\n"
        "Available tools:\n" + _AVAILABLE_TOOLS_DESCRIPTION
    )
    user = f"User context: {state.get('user_context', {})}\nUser query: {state['user_query']}"
    intent = llm_client.chat_json(system, user)
    if not intent:
        intent = {"intent": "unknown", "entities": {}, "requires_tools": ["weather_tool"]}
    logger.info("Understood intent: %s", intent)
    return {**state, "intent": intent}


def plan_tasks(state: OrchestratorState) -> OrchestratorState:
    intent = state.get("intent", {})
    system = (
        "You are the task-planning module of a disaster-early-warning orchestrator agent. "
        "Given the understood intent below, respond with ONLY a JSON object (no prose) of the form: "
        '{"tasks": [{"tool": "<tool_name>", "params": {...}}, ...]}. '
        "Only use tools from this list, and only include tools genuinely needed to answer the query:\n"
        + _AVAILABLE_TOOLS_DESCRIPTION
    )
    user = f"Intent: {intent}\nOriginal query: {state['user_query']}"
    plan = llm_client.chat_json(system, user)
    tasks = plan.get("tasks") if isinstance(plan, dict) else None
    if not tasks:
        # fall back to one task per tool the intent step already flagged
        entities = intent.get("entities", {})
        tasks = []
        for t in intent.get("requires_tools", []):
            p = {"query": state["user_query"], **entities}
            if t == "trip_tool":
                p["source"] = entities.get("source") or entities.get("location") or "Mandi"
                p["destination"] = entities.get("destination") or "Manali"
            tasks.append({"tool": t, "params": p})
    logger.info("Planned %d task(s): %s", len(tasks), tasks)
    return {**state, "task_plan": tasks}


def call_tools(state: OrchestratorState) -> OrchestratorState:
    tool_results: Dict[str, Dict[str, Any]] = {}
    agent_reports: Dict[str, Any] = {}
    tool_call_records = []
    errors = list(state.get("errors", []))

    for task in state.get("task_plan", []):
        tool_name = task.get("tool")
        params = task.get("params", {})
        result = call_tool(tool_name, params)
        tool_results[tool_name] = result

        # Extract or construct agent report for this tool
        agent_rep = result.get("agent_report")
        actions = result.get("actions_taken")
        if not agent_rep:
            tool_clean = tool_name.replace("_tool", "")
            actions = actions or [
                f"Invoked {tool_name} with params: {params}",
                f"Received result with status='{result.get('status', 'ok')}'",
                "Formatted structured agent output",
            ]
            agent_rep = {
                "agent_name": tool_clean,
                "agent_role": f"{tool_clean.replace('_', ' ').title()} Specialist",
                "status": "COMPLETED" if result.get("status") != "error" else "FAILED",
                "actions_taken": actions,
                "final_answer": {k: v for k, v in result.items() if k not in ("agent_report", "actions_taken")},
                "summary_markdown": f"### {tool_clean.replace('_', ' ').title()} Result\n- Status: `{result.get('status', 'ok')}`",
            }

        agent_reports[tool_name] = agent_rep
        tool_call_records.append({
            "tool": tool_name,
            "params": params,
            "result": result,
            "status": result.get("status", "unknown"),
            "actions_taken": actions,
            "agent_report": agent_rep,
        })
        if result.get("status") == "error":
            errors.append(f"{tool_name}: {result.get('note', 'unknown error')}")

    return {
        **state,
        "tool_results": tool_results,
        "tool_call_records": tool_call_records,
        "agent_reports": agent_reports,
        "errors": errors,
    }


def aggregate_and_validate(state: OrchestratorState) -> OrchestratorState:
    """Currently a pass-through + error surfacing; extend this with real
    cross-tool consistency checks once agents 2-8 return real data (e.g.
    flag if prediction_tool and alert_tool disagree on severity)."""
    tool_results = state.get("tool_results", {})
    if not tool_results:
        errors = list(state.get("errors", []))
        errors.append("No tools were called for this query.")
        return {**state, "errors": errors}
    return state


def generate_response(state: OrchestratorState) -> OrchestratorState:
    system = (
        "You are the response-generation module of a disaster-early-warning assistant for Himachal Pradesh. "
        "Given the user's query and the (possibly stubbed/placeholder) data gathered from specialized agents, "
        "write a clear, concise, natural-language answer. If any data is marked as a stub/placeholder, "
        "say the relevant capability isn't available yet rather than inventing numbers. "
        "Keep it to 2-4 sentences unless the query needs more detail."
    )
    user = (
        f"User query: {state['user_query']}\n"
        f"Intent: {state.get('intent', {})}\n"
        f"Tool results: {state.get('tool_results', {})}\n"
        f"Errors encountered: {state.get('errors', [])}"
    )
    response = llm_client.chat_text(system, user)
    logger.info("Generated response (%d chars)", len(response))
    return {**state, "final_response": response}


def finalize(state: OrchestratorState) -> OrchestratorState:
    conversation_memory.add_turn(state["session_id"], state["user_query"], state["final_response"])

    notifications = []
    alert_result = state.get("tool_results", {}).get("alert_tool")
    if alert_result and alert_result.get("status") == "ok" and alert_result.get("alert_level") not in (None, "unknown"):
        notifications.append({"type": "alert", "detail": alert_result})

    logger.info(
        "Finalized turn for session=%s | tools_used=%s | errors=%s",
        state["session_id"], [r["tool"] for r in state.get("tool_call_records", [])], state.get("errors", []),
    )
    return {**state, "notifications": notifications}


def build_orchestrator_graph():
    graph = StateGraph(OrchestratorState)

    graph.add_node("understand_intent", understand_intent)
    graph.add_node("plan_tasks", plan_tasks)
    graph.add_node("call_tools", call_tools)
    graph.add_node("aggregate_and_validate", aggregate_and_validate)
    graph.add_node("generate_response", generate_response)
    graph.add_node("finalize", finalize)

    graph.set_entry_point("understand_intent")
    graph.add_edge("understand_intent", "plan_tasks")
    graph.add_edge("plan_tasks", "call_tools")
    graph.add_edge("call_tools", "aggregate_and_validate")
    graph.add_edge("aggregate_and_validate", "generate_response")
    graph.add_edge("generate_response", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile()


orchestrator_graph = build_orchestrator_graph()
