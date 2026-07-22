import ast
import fnmatch
import io
import re
import tokenize
from pathlib import Path
from typing import Dict, List

from .base import CollectorBase, CollectedSource
from .helpers.file_readers import FileContent, read_file


# ----------------------------------------------------------------------
# Secret redaction — applied to everything that goes into the index,
# not just Python comments. Cheap defense-in-depth in case a real key
# or password was left in a comment, README snippet, or config sample.
# ----------------------------------------------------------------------
_SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key id
    re.compile(
        r"(?i)(api[_-]?key|secret[_-]?key|access[_-]?key|token|password|passwd|pwd)"
        r"\s*[:=]\s*['\"]?[A-Za-z0-9_\-\.]{8,}['\"]?"
    ),
]


def _redact_secrets(text: str) -> str:
    redacted = text
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def _extract_docs_and_comments(source_text: str) -> str:
    """
    Pull ONLY docstrings and '#' comments out of Python source — never
    the executable code itself. This is deliberate: whatever this
    function returns is the entire universe of what the RAG index can
    ever surface for a .py file. If a question asks to "show the code"
    or asks about something only present in code logic (a hardcoded
    value, a credential, business logic), there is nothing in the
    corpus to answer it with — the strict "answer only from context"
    rule in the prompt does the rest.
    """
    blocks = []

    # 1. Docstrings (module / class / function) via AST — line-accurate
    #    and doesn't depend on comment style or indentation.
    try:
        tree = ast.parse(source_text)
        module_doc = ast.get_docstring(tree)
        if module_doc:
            blocks.append((1, module_doc.strip()))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                doc = ast.get_docstring(node)
                if doc:
                    blocks.append((node.lineno, f"{node.name}: {doc.strip()}"))
    except SyntaxError:
        pass  # malformed/partial file — fall through to comments only

    # 2. Standalone "#" comments via tokenize — AST doesn't see these.
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source_text).readline)
        for tok in tokens:
            if tok.type == tokenize.COMMENT:
                text = tok.string.lstrip("#").strip()
                if text:
                    blocks.append((tok.start[0], text))
    except (tokenize.TokenizeError, IndentationError, SyntaxError):
        pass

    if not blocks:
        return ""

    blocks.sort(key=lambda b: b[0])
    joined = "\n".join(f"(line {ln}) {txt}" for ln, txt in blocks)
    return _redact_secrets(joined)


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

        text = file_content.text
        is_python = source.path.suffix.lower() == ".py"

        if is_python:
            # Never index raw code — only what the author documented
            # about it (docstrings/comments), with secrets redacted.
            text = _extract_docs_and_comments(text)
            if not text.strip():
                # Nothing worth indexing (no docstrings/comments at
                # all) — skip rather than push an empty chunk into
                # the index that would just confuse retrieval.
                return []
        else:
            # Defense in depth for README/config/text sources too.
            text = _redact_secrets(text)

        document_metadata = source.metadata.copy()
        document_metadata.update(file_content.metadata)
        document_metadata["content_type"] = "comments_only" if is_python else "full_text"

        return [
            {
                "page_content": text,
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