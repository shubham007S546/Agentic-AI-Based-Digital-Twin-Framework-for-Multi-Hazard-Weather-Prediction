"""RAG top-level package marker."""

import sys
from pathlib import Path

# Safeguard 1: Disable broken/mismatched torchvision in text-only pipeline to avoid torchvision::nms crash
if "torchvision" not in sys.modules:
    try:
        import torchvision
    except Exception:
        sys.modules["torchvision"] = None

# Safeguard 2: Ensure RAG's internal package directory takes precedence in sys.path
_rag_dir = str(Path(__file__).resolve().parent)
if _rag_dir in sys.path:
    sys.path.remove(_rag_dir)
sys.path.insert(0, _rag_dir)
