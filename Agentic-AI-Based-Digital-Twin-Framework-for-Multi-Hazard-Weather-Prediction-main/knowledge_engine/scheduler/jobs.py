from typing import Dict, List


class SchedulerJob:
    def __init__(self, name: str, targets: List[str], description: str) -> None:
        self.name = name
        self.targets = targets
        self.description = description


COLLECTOR_JOBS: Dict[str, SchedulerJob] = {
    "repo": SchedulerJob("repo", ["project"], "Ingest project repository content."),
    "government": SchedulerJob("government", ["government"], "Ingest government documents and PDFs."),
    "research": SchedulerJob("research", ["research"], "Ingest research papers and publications."),
    "datasets": SchedulerJob("datasets", ["datasets"], "Ingest dataset metadata and schema files."),
    "news": SchedulerJob("news", ["news"], "Ingest news articles and RSS feeds."),
    "all": SchedulerJob("all", ["project", "government", "research", "datasets", "news"], "Run all available collector groups."),
}
