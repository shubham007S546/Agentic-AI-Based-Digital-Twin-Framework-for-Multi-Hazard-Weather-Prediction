import argparse
from datetime import datetime

from knowledge_engine.orchestrator import KnowledgeEngine
from knowledge_engine.scheduler.scheduler import IngestionScheduler


def parse_args():
    parser = argparse.ArgumentParser(description="Knowledge Engine ingestion CLI")
    parser.add_argument("--repo", action="store_true", help="Ingest the project repository.")
    parser.add_argument("--government", action="store_true", help="Ingest government documents.")
    parser.add_argument("--research", action="store_true", help="Ingest research documents.")
    parser.add_argument("--datasets", action="store_true", help="Ingest dataset metadata.")
    parser.add_argument("--news", action="store_true", help="Ingest news feeds.")
    parser.add_argument("--all", action="store_true", help="Run all ingestion collectors.")
    parser.add_argument("--force", action="store_true", help="Reprocess sources even if unchanged.")
    parser.add_argument("--dry-run", action="store_true", help="Validate ingestion without persisting vectorstore content.")
    parser.add_argument("--since", type=str, help="Only ingest documents published after this ISO date.")
    parser.add_argument("--limit", type=int, help="Limit the number of sources ingested per target.")
    parser.add_argument("--schedule", type=str, choices=["manual", "daily", "weekly", "incremental"], default="manual", help="Run an ingestion schedule mode.")
    return parser.parse_args()


def main():
    args = parse_args()
    engine = KnowledgeEngine()
    scheduler = IngestionScheduler()

    if args.schedule != "manual":
        schedule = scheduler.schedule(args.schedule)
        targets = schedule["targets"]
        since = schedule["since"]
    else:
        targets = []
        if args.all:
            targets = ["project", "government", "research", "datasets", "news"]
        else:
            if args.repo:
                targets.append("project")
            if args.government:
                targets.append("government")
            if args.research:
                targets.append("research")
            if args.datasets:
                targets.append("datasets")
            if args.news:
                targets.append("news")
        since = datetime.fromisoformat(args.since) if args.since else None

    if not targets:
        raise ValueError("No ingest targets specified. Use --repo, --government, --research, --datasets, --news, or --all.")

    manifest = engine.run(targets=targets, force=args.force, dry_run=args.dry_run, since=since, limit=args.limit)
    print("Ingestion complete")
    print(manifest)


if __name__ == "__main__":
    main()
