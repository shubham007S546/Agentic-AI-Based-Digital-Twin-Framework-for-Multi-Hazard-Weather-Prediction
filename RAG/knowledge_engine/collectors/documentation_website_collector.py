import logging
from pathlib import Path
from typing import Any, Dict, List

import requests
from bs4 import BeautifulSoup

from .base import CollectorBase, CollectedSource

logger = logging.getLogger(__name__)


class DocumentationWebsiteCollector(CollectorBase):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.settings = self.config.get("collectors", {}).get("documentation", {})
        self.sites = list(self.settings.get("sites", []))

    def discover(self) -> List[CollectedSource]:
        sources = []
        for index, url in enumerate(self.sites, start=1):
            sources.append(CollectedSource(
                source_id=f"documentation_site_{index}",
                source_type="documentation_site",
                path=Path(url),
                metadata={
                    "collection": "manuals",
                    "source": url,
                    "document_type": "html",
                    "url": url,
                },
            ))
        return sources

    def fetch(self, source: CollectedSource) -> List[object]:
        try:
            response = requests.get(source.metadata["url"], timeout=20)
            response.raise_for_status()
        except Exception as exc:
            logger.warning(f"Documentation site fetch failed for {source.metadata.get('url')}: {exc}")
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        title = soup.title.string.strip() if soup.title and soup.title.string else "Documentation"
        main_text = []
        for section in soup.find_all(["article", "main", "section", "div"]):
            paragraphs = [p.get_text(strip=True) for p in section.find_all("p") if p.get_text(strip=True)]
            if paragraphs:
                main_text.append("\n\n".join(paragraphs))
        text = "\n\n".join(main_text) or "\n\n".join([p.get_text(strip=True) for p in soup.find_all("p") if p.get_text(strip=True)])

        return [{
            "page_content": text,
            "metadata": {
                **source.metadata,
                "source_type": "documentation_site",
                "title": title,
            },
        }]
