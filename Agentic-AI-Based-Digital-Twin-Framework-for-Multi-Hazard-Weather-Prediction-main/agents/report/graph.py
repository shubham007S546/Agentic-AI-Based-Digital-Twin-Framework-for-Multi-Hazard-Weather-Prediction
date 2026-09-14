"""
The Report Generation Agent's LangGraph state machine -- implements the
diagram's 7-step workflow:

    1. Receive report request     -> (entry, see main.py)
    2. Collect data                -> collect_data_node
    3. Process & analyze           -> process_and_analyze_node
    4. Generate insights           -> generate_insights_node
    5. Create report               -> create_report_node
    6. Export & distribute         -> export_and_distribute_node
    7. Log & store                 -> log_and_store_node
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from langgraph.graph import END, StateGraph

from . import data_aggregator
from .analytics import analyze
from .config import settings
from .distribution import distribute_report
from .export import export_report
from .insight_extractor import generate_insights
from .logging_config import get_logger
from .report_builder import build_sections
from .schemas import ReportState
from .storage import report_store

logger = get_logger(__name__)


def collect_data_node(state: ReportState) -> ReportState:
    request = state["request"]
    collected = data_aggregator.collect_data(
        request["report_type"], request["districts"], request.get("horizon", "24h"),
        data_override=request.get("data_override"),
    )
    return {**state, "collected_data": collected["per_district"],
            "data_sources_used": collected["sources_used"], "data_completeness": collected["completeness"]}


def process_and_analyze_node(state: ReportState) -> ReportState:
    request = state["request"]
    analysis = analyze(state["collected_data"], request["districts"])
    return {**state, "analysis": analysis}


def generate_insights_node(state: ReportState) -> ReportState:
    request = state["request"]
    result = generate_insights(state["analysis"], request["report_type"], request["districts"])
    return {**state, "insights": result["insights"], "summary": result["summary"]}


def create_report_node(state: ReportState) -> ReportState:
    request = state["request"]
    sections = build_sections(
        state["analysis"], state["insights"], state["summary"],
        request["report_type"], request.get("include_charts", True),
    )
    report_id = report_store.new_report_id()
    version = report_store.next_version(request["report_type"], request["districts"])
    return {**state, "sections": sections, "report_id": report_id, "version": version}


def export_and_distribute_node(state: ReportState) -> ReportState:
    request = state["request"]
    metadata = {
        "report_id": state["report_id"], "report_type": request["report_type"],
        "format": request.get("format", "pdf"), "version": state["version"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "districts": request["districts"], "data_sources_used": state["data_sources_used"],
        "data_completeness": state["data_completeness"],
    }
    export_result = export_report(state["sections"], metadata, request.get("format", "pdf"),
                                   settings.reports_output_dir)

    distribution = distribute_report(
        state["report_id"], export_result["file_path"],
        request.get("distribute", False), request.get("notification_channels", []),
    )

    return {**state, "file_path": export_result["file_path"], "distribution": distribution, "metadata": metadata}


def log_and_store_node(state: ReportState) -> ReportState:
    request = state["request"]
    metadata = state["metadata"]

    result = {
        "metadata": metadata,
        "summary": state["summary"],
        "key_insights": state["insights"],
        "sections": state["sections"],
        "file_path": state["file_path"],
        "download_url": f"/api/v1/reports/{state['report_id']}/download",
        "distribution": state["distribution"],
        "notes": [f"data_completeness={state['data_completeness']}"],
    }

    report_store.save(result)
    logger.info("Report %s (v%d) stored | type=%s | format=%s | completeness=%.2f",
                state["report_id"], state["version"], request["report_type"],
                request.get("format", "pdf"), state["data_completeness"])

    return {**state, "result": result}


def build_report_graph():
    graph = StateGraph(ReportState)

    graph.add_node("collect_data", collect_data_node)
    graph.add_node("process_and_analyze", process_and_analyze_node)
    graph.add_node("generate_insights", generate_insights_node)
    graph.add_node("create_report", create_report_node)
    graph.add_node("export_and_distribute", export_and_distribute_node)
    graph.add_node("log_and_store", log_and_store_node)

    graph.set_entry_point("collect_data")
    graph.add_edge("collect_data", "process_and_analyze")
    graph.add_edge("process_and_analyze", "generate_insights")
    graph.add_edge("generate_insights", "create_report")
    graph.add_edge("create_report", "export_and_distribute")
    graph.add_edge("export_and_distribute", "log_and_store")
    graph.add_edge("log_and_store", END)

    return graph.compile()


report_graph = build_report_graph()
