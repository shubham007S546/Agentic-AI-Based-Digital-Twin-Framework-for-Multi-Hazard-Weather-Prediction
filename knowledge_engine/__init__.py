import os

# Shim to make `import knowledge_engine` continue to work after moving the
# package contents under RAG_project/knowledge_engine. This sets the
# package search path to the moved location so existing imports remain valid.

_this_dir = os.path.dirname(__file__)
_repo_root = os.path.dirname(_this_dir)  # one level above this shim
_moved_path = os.path.join(_repo_root, "RAG_project", "knowledge_engine")

# If the moved path exists, use it as the package path. Otherwise fall back to
# the original location (best-effort compatibility during incremental changes).
if os.path.isdir(_moved_path):
    __path__ = [os.path.abspath(_moved_path)]
else:
    __path__ = [os.path.abspath(_this_dir)]
