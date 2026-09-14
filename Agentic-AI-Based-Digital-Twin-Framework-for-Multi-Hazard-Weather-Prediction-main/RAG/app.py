"""
app.py
------
WORKFLOW 2 — Runtime chat application.

Loads the FAISS index + processed chunks produced by build_index.py,
rebuilds BM25 in-memory (cheap — no embeddings involved), wires up the
HybridRetriever + RAGChain, and starts the interactive chat loop.

This script NEVER re-embeds or rebuilds the FAISS index. If the source
PDFs changed, run `python build_index.py` first.
"""

import sys
from pathlib import Path

_rag_root = str(Path(__file__).resolve().parent)
if _rag_root in sys.path:
    sys.path.remove(_rag_root)
sys.path.insert(0, _rag_root)

# Safeguard against torchvision::nms mismatch
if "torchvision" not in sys.modules:
    try:
        import torchvision
    except Exception:
        sys.modules["torchvision"] = None

from retriever.hybrid import HybridRetriever
from chains.rag_chain import RAGChain
from utils.singletons import get_faiss_store
from utils.logger import logger


def load_runtime_dependencies():
    """Load the persisted FAISS index + chunks. No PDF parsing, no
    chunking, no embedding generation happens here — all of that only
    ever runs inside build_index.py."""

    # Singleton-cached: loaded from disk exactly once per process.
    # vector_db.load() (inside get_faiss_store) reads both index.faiss
    # AND documents.pkl, so the exact same chunk list used to build the
    # index comes along for free — no separate chunks file needed.
    vector_db = get_faiss_store()
    print("Vector Database Loaded")
    print("Total Vectors :", vector_db.index.ntotal)

    chunks = vector_db.documents
    if not chunks:
        raise RuntimeError(
            "FAISS index loaded but has no documents. "
            "Run `python build_index.py` first."
        )
    print(f"Chunks Loaded : {len(chunks)}")

    # BM25 rebuilt over the SAME chunks used for FAISS, so both
    # retrieval paths share identical text/metadata + chunk_id.
    hybrid_retriever = HybridRetriever(chunks)
    return hybrid_retriever


def main():
    print("\n" + "=" * 80)
    print("Research Paper RAG")
    print("=" * 80)

    hybrid_retriever = load_runtime_dependencies()

    # Inject the hybrid retriever so RAGChain uses
    # FAISS + BM25 + RRF + Cross-Encoder instead of plain vector search
    rag = RAGChain(retriever=hybrid_retriever)

    while True:
        print()
        question = input("Ask a Question (type 'exit' to quit): ")

        if question.lower() == "exit":
            print("\nGoodbye!")
            break

        try:
            response = rag.ask(question)

            print("\n" + "=" * 80)
            print("ANSWER")
            print("=" * 80)
            print(response["answer"])

            print("\n" + "=" * 80)
            print("SOURCES")
            print("=" * 80)
            for source in response["sources"]:
                print(f"• {source}")

            print("\n" + "=" * 80)
            print("MEMORY (conversation history so far)")
            print("=" * 80)
            print(rag.memory.get_context())

        except Exception as e:
            logger.error(f"Error handling question: {e}")
            print(f"\nError: {e}")


if __name__ == "__main__":
    main()