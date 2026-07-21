"""Create Report, matching the diagram's "Create Report" step and "Report
Builder" component. Builds a format-agnostic list of sections (text/table/
chart); export.py then renders these into PDF/Excel/JSON."""

from __future__ import annotations

from typing import Any, Dict, List

from .logging_config import get_logger

logger = get_logger(__name__)


def build_sections(analysis: Dict[str, Any], insights: List[str], summary: str,
                    report_type: str, include_charts: bool) -> List[Dict[str, Any]]:
    sections: List[Dict[str, Any]] = [
        {"title": "Summary", "kind": "text", "content": summary},
        {"title": "Key Insights", "kind": "text", "content": "\n".join(f"- {i}" for i in insights)},
    ]

    district_metrics = analysis.get("district_metrics", {})
    if district_metrics:
        rows = []
        for district, metrics in district_metrics.items():
            rows.append({
                "District": district,
                "Temp (C)": metrics.get("current_temperature"),
                "Humidity (%)": metrics.get("current_humidity"),
                "Predicted Rainfall (mm)": metrics.get("predicted_rainfall_mm"),
                "Digital Twin Risk": metrics.get("digital_twin_risk_level"),
                "Landslide Score": metrics.get("landslide_susceptibility_score"),
            })
        sections.append({"title": "District Metrics", "kind": "table", "content": rows})

        if include_charts:
            chart_data = {d: m.get("predicted_rainfall_mm") for d, m in district_metrics.items()
                          if m.get("predicted_rainfall_mm") is not None}
            if chart_data:
                sections.append({"title": "Predicted Rainfall by District", "kind": "chart",
                                  "content": {"type": "bar", "data": chart_data, "ylabel": "Rainfall (mm)"}})

    alert_summary = analysis.get("alert_summary", {})
    if alert_summary.get("total_active", 0) > 0:
        sections.append({"title": "Active Alerts", "kind": "table",
                          "content": [{"Metric": "Total Active", "Value": alert_summary["total_active"]}] +
                                     [{"Metric": f"Severity: {k}", "Value": v}
                                      for k, v in alert_summary.get("by_severity", {}).items()]})
        if include_charts and alert_summary.get("by_severity"):
            sections.append({"title": "Alerts by Severity", "kind": "chart",
                              "content": {"type": "pie", "data": alert_summary["by_severity"]}})

    logger.info("Built %d report section(s) for report_type=%s", len(sections), report_type)
    return sections
