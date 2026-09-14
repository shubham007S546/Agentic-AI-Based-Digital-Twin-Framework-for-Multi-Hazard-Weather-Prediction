import os

# Shim: `knowledge_engine` package contents live inside `RAG/knowledge_engine/`.
# The folder was originally called `RAG_project/knowledge_engine` but the parent
# was renamed to `RAG/`. This shim re-points __path__ so that
# `from knowledge_engine.xxx import yyy` resolves correctly.

_this_dir = os.path.dirname(__file__)
_repo_root = os.path.dirname(_this_dir)  # one level above this shim

# Primary location: RAG/knowledge_engine (current name after rename)
_moved_path = os.path.join(_repo_root, "RAG", "knowledge_engine")
# Legacy fallback: RAG_project/knowledge_engine (old name — kept for safety)
_legacy_path = os.path.join(_repo_root, "RAG_project", "knowledge_engine")

if os.path.isdir(_moved_path):
    __path__ = [os.path.abspath(_moved_path)]
elif os.path.isdir(_legacy_path):
    __path__ = [os.path.abspath(_legacy_path)]
else:
    __path__ = [os.path.abspath(_this_dir)]
