import re
from datetime import datetime
from typing import Dict, Optional

from .hazard_identifier import HazardIdentifier


class MetadataExtractor:
    DATE_PATTERNS = [
        r"\b(\d{4}-\d{2}-\d{2})\b",
        r"\b(\d{1,2}/\d{1,2}/\d{2,4})\b",
        r"\b(\d{1,2}\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})\b",
    ]

    ORGANIZATION_PATTERNS = [
        r"\b(University|Institute|Agency|Department|Ministry|Government|Corporation|Center|Centre)\b",
    ]

    def __init__(self) -> None:
        self.hazard_identifier = HazardIdentifier()

    def extract(self, text: str, metadata: Dict[str, object]) -> Dict[str, object]:
        enriched = metadata.copy()
        enriched.setdefault("title", self._extract_title(text, metadata))
        enriched.setdefault("language", self._detect_language(text))
        enriched.setdefault("organization", self._extract_organization(text, metadata))
        enriched.setdefault("hazard", self._extract_hazard(text, metadata))
        enriched.setdefault("publication_date", self._extract_publication_date(text, metadata))
        enriched.setdefault("authors", self._extract_authors(text, metadata))
        return enriched

    def _extract_title(self, text: str, metadata: Dict[str, object]) -> str:
        if metadata.get("title"):
            return str(metadata["title"])

        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                return stripped.lstrip("# ")
            if len(stripped) < 120 and any(ch.isalpha() for ch in stripped):
                return stripped
        return metadata.get("file_name", "Untitled")

    def _detect_language(self, text: str) -> str:
        try:
            from langdetect import detect

            return detect(text)
        except Exception:
            return "unknown"

    def _extract_organization(self, text: str, metadata: Dict[str, object]) -> Optional[str]:
        if metadata.get("organization"):
            return str(metadata["organization"])

        for pattern in self.ORGANIZATION_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    def _extract_hazard(self, text: str, metadata: Dict[str, object]) -> Optional[str]:
        if metadata.get("hazard"):
            return str(metadata["hazard"])
        return self.hazard_identifier.identify(text)

    def _extract_publication_date(self, text: str, metadata: Dict[str, object]) -> Optional[str]:
        if metadata.get("publication_date"):
            return str(metadata["publication_date"])

        for pattern in self.DATE_PATTERNS:
            match = re.search(pattern, text)
            if match:
                candidate = match.group(1)
                parsed = self._normalize_date(candidate)
                if parsed:
                    return parsed
        return None

    def _normalize_date(self, candidate: str) -> Optional[str]:
        for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d %B %Y"]:
            try:
                return datetime.strptime(candidate, fmt).date().isoformat()
            except ValueError:
                continue
        return None

    def _extract_authors(self, text: str, metadata: Dict[str, object]) -> Optional[str]:
        if metadata.get("authors"):
            return metadata["authors"]

        author_regex = re.compile(r"\b([A-Z][a-z]+\s+[A-Z][a-z]+(?:,\s*[A-Z][a-z]+\s+[A-Z][a-z]+)*)\b")
        match = author_regex.search(text[:1000])
        if match:
            return match.group(1)
        return None
