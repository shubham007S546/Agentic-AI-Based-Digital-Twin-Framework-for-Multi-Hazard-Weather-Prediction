"""
RAG_project — compatibility shim.

The package was renamed from ``RAG_project/`` to ``RAG/`` at the repo root.
This shim makes ``from RAG_project.X.Y import Z`` transparently resolve to
``RAG/X/Y.py :: Z`` so no existing import statement elsewhere needs to change.

How it works
------------
Python resolves ``import RAG_project`` by finding *this* ``__init__.py``.
We then repoint ``__path__`` to the real ``RAG/`` directory, so every
subsequent ``from RAG_project.<module>`` lookup is served from ``RAG/``.
"""
from __future__ import annotations

import os as _os
import sys as _sys
from pathlib import Path as _Path

# Absolute path to the real RAG package directory (sibling of this folder).
_RAG_DIR = str((_Path(__file__).resolve().parent.parent / "RAG").resolve())

# Ensure RAG/ itself is importable as a top-level package as well.
if _RAG_DIR not in _sys.path:
    _sys.path.insert(0, str(_Path(_RAG_DIR).parent))

# Redirect all sub-module lookups for ``RAG_project.*`` to ``RAG/``.
__path__ = [_RAG_DIR]

# Make ``import RAG_project`` also expose the RAG package's __version__ etc.
# (best-effort — does not fail if RAG has no __version__).
try:
    from RAG import *  # noqa: F401, F403
except Exception:
    pass
