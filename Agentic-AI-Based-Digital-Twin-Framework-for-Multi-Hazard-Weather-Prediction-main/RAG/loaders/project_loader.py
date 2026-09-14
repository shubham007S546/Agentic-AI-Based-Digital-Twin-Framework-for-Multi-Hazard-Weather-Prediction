"""
Project Documentation Loader for RAG.
Ingests project READMEs, architecture documents, dataset schemes, and run guides
so that the RAG pipeline can answer questions about the current project.
"""

from pathlib import Path
from typing import List
from loaders.pdf_loader import Document
from utils.logger import logger


class ProjectLoader:
    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)

    def load_project_docs(self) -> List[Document]:
        docs: List[Document] = []
        target_docs = [
            "README.md",
            "RUN_GUIDE.md",
            "DATASET_SCHEME.md",
            "MODEL_TRAINING_PLAN.md",
            "PROJECT_PROGESS.md",
            "config/config.yaml",
            "agents/orchestrator/README.md",
            "agents/weather_analysis/README.md",
            "agents/alert_risk/README.md",
            "agents/report/README.md",
            "agents/digital_twin/README.md",
            "agents/prediction/README.md",
        ]

        for rel_path in target_docs:
            p = self.repo_root / rel_path
            if p.exists():
                try:
                    text = p.read_text(encoding="utf-8", errors="replace")
                    if text.strip():
                        docs.append(
                            Document(
                                page_content=text,
                                metadata={
                                    "source": rel_path,
                                    "page": 1,
                                    "doc_type": "project_documentation",
                                },
                            )
                        )
                        logger.info("Loaded project document: %s (%d chars)", rel_path, len(text))
                except Exception as exc:
                    logger.warning("Failed reading %s: %s", rel_path, exc)

        logger.info("ProjectLoader loaded %d documents", len(docs))
        return docs
