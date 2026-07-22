from datetime import datetime, timedelta
from typing import Dict, List, Optional

from ..config.config import config
from .jobs import COLLECTOR_JOBS


class IngestionScheduler:
    def __init__(self) -> None:
        self.schedule_config = config.get("scheduler", {})

    def resolve_targets(self, mode: str) -> List[str]:
        if mode == "manual":
            return []
        if mode == "daily":
            return [job_name for job_name in COLLECTOR_JOBS if job_name != "all"]
        if mode == "weekly":
            return [job_name for job_name in COLLECTOR_JOBS if job_name != "all"]
        if mode == "incremental":
            return [job_name for job_name in COLLECTOR_JOBS if job_name != "all"]
        return []

    def compute_since(self, mode: str) -> Optional[datetime]:
        now = datetime.utcnow()
        if mode == "daily":
            return now - timedelta(days=1)
        if mode == "weekly":
            return now - timedelta(days=7)
        if mode == "incremental":
            window = int(self.schedule_config.get("incremental_window_days", 1))
            return now - timedelta(days=window)
        return None

    def schedule(self, mode: str) -> Dict[str, object]:
        return {
            "mode": mode,
            "targets": self.resolve_targets(mode),
            "since": self.compute_since(mode),
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
