from pathlib import Path
from typing import Any, Dict, List

from .base import CollectorBase, CollectedSource
from .helpers.file_readers import FileContent, read_file


class DatasetMetadataCollector(CollectorBase):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.settings = self.config.get("collectors", {}).get("datasets", {})
        self.directories = [Path(d).resolve() for d in self.settings.get("directories", [])]
        self.metadata_extensions = {".json", ".yaml", ".yml", ".csv", ".txt", ".md"}

    def discover(self) -> List[CollectedSource]:
        sources = []
        for directory in self.directories:
            if not directory.exists():
                continue
            for path in directory.rglob("*"):
                if path.is_file() and path.suffix.lower() in self.metadata_extensions:
                    source_id = str(path.relative_to(directory))
                    sources.append(CollectedSource(
                        source_id=source_id,
                        source_type="dataset_metadata",
                        path=path,
                        metadata={
                            "collection": "datasets",
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
            raise RuntimeError(f"Failed to read dataset metadata {source.path}: {exc}") from exc

        metadata = {**source.metadata, **file_content.metadata, "source_type": "dataset_metadata"}
        return [{"page_content": file_content.text, "metadata": metadata}]
