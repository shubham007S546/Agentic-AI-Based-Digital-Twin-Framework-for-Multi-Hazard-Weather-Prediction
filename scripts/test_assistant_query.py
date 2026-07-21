import os
import sys
import json
from pathlib import Path

# Ensure the repository root is on sys.path so imports like `RAG_project` resolve
_repo_root = str(Path(__file__).resolve().parent.parent)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

# Simple test runner that invokes the RAG runtime used by the backend assistant.
# Usage: python scripts/test_assistant_query.py "Your question"

question = sys.argv[1] if len(sys.argv) > 1 else "What is the purpose of this project?"

try:
    from RAG_project.app import load_runtime_dependencies
    from RAG_project.chains.rag_chain import RAGChain

    retriever = load_runtime_dependencies()
    rag = RAGChain(retriever)
    result = rag.ask(question)

    # Sanitize common types for JSON output
    if isinstance(result, dict):
        answer = result.get("answer") or result.get("answer_text") or str(result.get("answer", ""))
        sources_raw = result.get("sources", [])
        sources = [str(s) for s in sources_raw]
        out = {"ok": True, "answer": answer, "sources": sources}
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(json.dumps({"ok": True, "result_str": str(result)}, ensure_ascii=False))

except Exception as exc:
    print(json.dumps({"ok": False, "error": str(exc)}))
