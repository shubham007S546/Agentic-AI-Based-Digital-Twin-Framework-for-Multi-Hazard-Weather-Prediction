import fnmatch
from pathlib import Path
from typing import Dict, List

from .base import CollectorBase, CollectedSource
from .helpers.file_readers import FileContent, read_file


class ProjectRepositoryCollector(CollectorBase):
    DEFAULT_EXTENSIONS = {
        ".md",
        ".markdown",
        ".py",
        ".json",
        ".yaml",
        ".yml",
        ".ipynb",
        ".txt",
        ".rst",
    }
    DEFAULT_FILENAMES = {"README.md", "README", "README.rst", "Dockerfile", "requirements.txt"}

    def __init__(self, config: Dict[str, object]):
        super().__init__(config)
        self.settings = self.config.get("collectors", {}).get("project_repo", {})
        self.root_dir = Path(self.settings.get("root_dir", ".")).resolve()
        self.ignored = set(self.settings.get("ignore", []))
        self.extensions = set(self.settings.get("supported_extensions", [])) or self.DEFAULT_EXTENSIONS

    def discover(self) -> List[CollectedSource]:
        import os

        sources = []
        for root, dirs, files in os.walk(self.root_dir):
           root_path = Path(root)
           # Remove ignored directories from traversal
           dirs[:] = [d for d in dirs if not self._is_ignored(root_path / d)]
           for filename in files:
               path = root_path / filename
               if self._is_ignored(path):
                   continue
               if self._is_allowlisted_file(path):
                   source_id = str(path.relative_to(self.root_dir))
                   sources.append(CollectedSource(
                       source_id=source_id,
                       source_type="project_repo",
                       path=path,
                       metadata={
                           "collection": "project",
                           "source": source_id,
                           "document_type": self._document_type(path),
                           "file_path": str(path),
                       },
                   ))
        return sources

    def fetch(self, source: CollectedSource) -> List[object]:
        if not source.path.exists():
            return []

        try:
            file_content = read_file(source.path)
        except Exception as exc:
            raise RuntimeError(f"Failed to read project repository file {source.path}: {exc}") from exc

        document_metadata = source.metadata.copy()
        document_metadata.update(file_content.metadata)

        return [
            {
                "page_content": file_content.text,
                "metadata": {
                    **document_metadata,
                    "source_type": "project_repo",
                },
            }
        ]

    def _is_ignored(self, path: Path) -> bool:
        relative = path.relative_to(self.root_dir)
        text = str(relative).replace("\\", "/")
        if any(part.startswith(".") for part in relative.parts if part != "."):
            return True
        if any(fnmatch.fnmatch(text, pattern) for pattern in self.ignored):
            return True
        return False

    def _is_allowlisted_file(self, path: Path) -> bool:
        if path.name in self.DEFAULT_FILENAMES:
            return True
        if path.suffix.lower() in self.extensions:
            return True
        return False

    def _document_type(self, path: Path) -> str:
        if path.name.lower() in self.DEFAULT_FILENAMES:
            return path.name.lower()
        return path.suffix.lower().lstrip('.')
