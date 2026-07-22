import logging
from pathlib import Path
from typing import Any, Dict, List

import requests
from bs4 import BeautifulSoup

from .base import CollectorBase, CollectedSource

logger = logging.getLogger(__name__)


class NewsCollector(CollectorBase):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.settings = self.config.get("collectors", {}).get("news", {})
        self.feeds = list(self.settings.get("rss_feeds", []))
        self.urls = list(self.settings.get("urls", []))

    def discover(self) -> List[CollectedSource]:
        sources: List[CollectedSource] = []
        for index, url in enumerate(self.urls, start=1):
            sources.append(CollectedSource(
                source_id=f"news_url_{index}",
                source_type="news_url",
                path=Path(url),
                metadata={
                    "collection": "news",
                    "source": url,
                    "document_type": "html",
                    "url": url,
                },
            ))
        # RSS support is available through feed URLs and does not require a local file path.
        for index, rss_url in enumerate(self.feeds, start=1):
            sources.append(CollectedSource(
                source_id=f"news_rss_{index}",
                source_type="news_rss",
                path=Path(rss_url),
                metadata={
                    "collection": "news",
                    "source": rss_url,
                    "document_type": "rss",
                    "url": rss_url,
                },
            ))
        return sources

    def fetch(self, source: CollectedSource) -> List[object]:
        try:
            response = requests.get(source.metadata["url"], timeout=20)
            response.raise_for_status()
        except Exception as exc:
            logger.warning(f"News fetch failed for {source.metadata.get('url')}: {exc}")
            return []

        if source.source_type == "news_rss":
            # RSS contains XML, so we simply preserve the raw feed if parsing isn't available.
            text = response.text
            return [{"page_content": text, "metadata": {**source.metadata, "source_type": "news_rss"}}]

        soup = BeautifulSoup(response.text, "html.parser")
        paragraphs = [p.get_text(strip=True) for p in soup.find_all("p") if p.get_text(strip=True)]
        return [{
            "page_content": "\n\n".join(paragraphs),
            "metadata": {**source.metadata, "source_type": "news_url"},
        }]
