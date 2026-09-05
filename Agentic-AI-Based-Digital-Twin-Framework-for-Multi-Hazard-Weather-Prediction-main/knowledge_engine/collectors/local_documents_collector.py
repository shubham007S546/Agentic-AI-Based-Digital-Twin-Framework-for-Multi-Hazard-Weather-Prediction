from pathlib import Path
from typing import Dict, List

from .base import CollectorBase, CollectedSource
from .helpers.file_readers import FileContent, read_file


class LocalDocumentsCollector(CollectorBase):
    def __init__(self, config: Dict[str, object]):
        super().__init__(config)
        self.settings = self.config.get("collectors", {}).get("local_documents", {})
        self.directories = [Path(d).resolve() for d in self.settings.get("directories", [])]
        self.extensions = set(self.settings.get("supported_extensions", []))

    def discover(self) -> List[CollectedSource]:
        sources = []
        for directory in self.directories:
            if not directory.exists():
                continue
            for path in directory.rglob("*"):
                if path.is_file() and self._is_supported(path):
                    source_id = str(path.relative_to(directory))
                    sources.append(CollectedSource(
                        source_id=source_id,
                        source_type="local_document",
                        path=path,
                        metadata={
                            "collection": "reports",
                            "source": source_id,
                            "document_type": path.suffix.lower().lstrip('.'),
                            "file_path": str(path),
                        },
                    ))
        return sources

    def fetch(self, source: CollectedSource) -> List[object]:
        try:
            file_content = read_file(source.path)
        except Exception as exc:
            raise RuntimeError(f"Failed to read local document {source.path}: {exc}") from exc

        metadata = source.metadata.copy()
        metadata.update(file_content.metadata)
        metadata["source_type"] = "local_document"
        return [
            {
                "page_content": file_content.text,
                "metadata": metadata,
            }
        ]

    def _is_supported(self, path: Path) -> bool:
        extension = path.suffix.lower()
        return extension in self.extensions
