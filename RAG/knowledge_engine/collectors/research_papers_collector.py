import logging
from pathlib import Path
from typing import Any, Dict, List

import requests
from bs4 import BeautifulSoup

from .base import CollectorBase, CollectedSource
from .helpers.file_readers import FileContent, read_file

logger = logging.getLogger(__name__)


class ResearchPapersCollector(CollectorBase):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.settings = self.config.get("collectors", {}).get("research", {})
        self.directories = [Path(d).resolve() for d in self.settings.get("local_directories", [])]
        self.urls = list(self.settings.get("urls", []))

    def discover(self) -> List[CollectedSource]:
        sources = []
        for directory in self.directories:
            if not directory.exists():
                continue
            for path in directory.rglob("*"):
                if path.is_file():
                    source_id = str(path.relative_to(directory))
                    sources.append(CollectedSource(
                        source_id=source_id,
                        source_type="research_document",
                        path=path,
                        metadata={
                            "collection": "research",
                            "source": source_id,
                            "document_type": path.suffix.lower().lstrip('.'),
                            "file_path": str(path),
                        },
                    ))
        for index, url in enumerate(self.urls, start=1):
            sources.append(CollectedSource(
                source_id=f"research_url_{index}",
                source_type="research_url",
                path=Path(url),
                metadata={
                    "collection": "research",
                    "source": url,
                    "document_type": "html",
                    "url": url,
                },
            ))
        return sources

    def fetch(self, source: CollectedSource) -> List[object]:
        if source.source_type == "research_url":
            try:
                response = requests.get(source.metadata["url"], timeout=20)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")
                paragraphs = [p.get_text(strip=True) for p in soup.find_all("p") if p.get_text(strip=True)]
                return [{
                    "page_content": "\n\n".join(paragraphs),
                    "metadata": {
                        **source.metadata,
                        "source_type": "research_url",
                    },
                }]
            except Exception as exc:
                logger.warning(f"Research URL fetch failed for {source.metadata.get('url')}: {exc}")
                return []

        try:
            file_content = read_file(source.path)
        except Exception as exc:
            logger.warning(f"Research document read failed for {source.path}: {exc}")
            return []

        metadata = {**source.metadata, **file_content.metadata, "source_type": "research_document"}
        return [{"page_content": file_content.text, "metadata": metadata}]
