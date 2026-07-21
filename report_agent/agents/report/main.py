"""
FastAPI entrypoint for the Report Generation Agent (Agent 6 of 8).

Run with:
    uvicorn agents.report.main:app --reload --port 8005

Endpoints (matching the architecture diagram):
    POST /api/v1/reports/generate
    GET  /api/v1/reports/templates
    GET  /api/v1/reports/{report_id}
    GET  /api/v1/reports/{report_id}/download
"""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .graph import report_graph
from .logging_config import get_logger
from .schemas import REPORT_FORMATS, REPORT_TYPES, ReportRequest, ReportResult
from .storage import report_store

logger = get_logger(__name__)

app = FastAPI(
    title="Report Generation Agent",
    description="Agent 6 of 8 -- automated insights & report generation (PDF/Excel/JSON).",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/v1/reports/templates")
def templates() -> dict:
    return {"report_types": REPORT_TYPES, "formats": REPORT_FORMATS}


@app.post("/api/v1/reports/generate", response_model=ReportResult)
def generate(request: ReportRequest) -> ReportResult:
    try:
        initial_state = {"request": request.model_dump(), "errors": []}
        final_state = report_graph.invoke(initial_state)
        return ReportResult(**final_state["result"])
    except Exception as exc:
        logger.exception("Report generation failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/v1/reports/{report_id}")
def get_report(report_id: str) -> dict:
    record = report_store.get(report_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    return record


@app.get("/api/v1/reports/{report_id}/download")
def download_report(report_id: str) -> FileResponse:
    record = report_store.get(report_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    file_path = record.get("file_path")
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Report file not found on disk.")
    return FileResponse(file_path, filename=os.path.basename(file_path))


@app.get("/api/v1/reports")
def list_reports(limit: int = 20) -> list:
    return report_store.list_recent(limit)
