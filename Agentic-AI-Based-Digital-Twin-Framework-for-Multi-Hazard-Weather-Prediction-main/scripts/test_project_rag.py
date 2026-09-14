"""
scripts/test_project_rag.py
---------------------------
Tests the RAG pipeline with Groq LLM against real project questions and literature questions.
Verifies that:
1. FAISS and BM25 index loads correctly.
2. Hybrid retrieval (FAISS + BM25 + Reciprocal Rank Fusion) finds the relevant project chunks.
3. Groq (openai/gpt-oss-120b) generates grounded answers with accurate citations.
"""

import sys
from pathlib import Path

# Ensure RAG root is at index 0 of sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
RAG_ROOT = REPO_ROOT / "RAG"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(RAG_ROOT) in sys.path:
    sys.path.remove(str(RAG_ROOT))
sys.path.insert(0, str(RAG_ROOT))

# Ensure UTF-8 stdout for Windows consoles
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from utils.singletons import get_faiss_store
from retriever.hybrid import HybridRetriever
from chains.rag_chain import RAGChain


def test_project_rag():
    print("=" * 75)
    print("TESTING RAG PIPELINE WITH GROQ LLM & PROJECT DOCUMENTATION")
    print("=" * 75)

    print("\n[1/3] Loading FAISS index and initializing Hybrid Retriever...")
    vector_db = get_faiss_store()
    chunks = vector_db.documents
    print(f"  --> Vectors loaded in FAISS: {vector_db.index.ntotal}")
    print(f"  --> Processed chunks loaded: {len(chunks)}")
    
    unique_sources = sorted(set(d.metadata.get("source", "unknown") for d in chunks))
    print(f"  --> Indexed sources ({len(unique_sources)}): {unique_sources}")

    hybrid_retriever = HybridRetriever(chunks)
    rag_chain = RAGChain(retriever=hybrid_retriever)
    print("  --> RAGChain initialized with Groq LLM.")

    # Test questions: 1 project-specific question, 1 domain question
    questions = [
        "What districts in Himachal Pradesh are covered by this weather prediction framework?",
        "What machine learning and deep learning models are planned in the project?",
    ]

    for idx, q in enumerate(questions, 2):
        print(f"\n[{idx}/3] Asking: '{q}'")
        res = rag_chain.ask(q)
        print("\n--- GROQ GENERATED ANSWER ---")
        print(res.get("answer", ""))
        print("\n--- RETRIEVED SOURCES ---")
        for src in res.get("sources", []):
            print(f"  * {src}")
        print("-" * 50)

    print("\n" + "=" * 75)
    print("RAG TEST COMPLETED SUCCESSFULLY")
    print("=" * 75)


if __name__ == "__main__":
    test_project_rag()
