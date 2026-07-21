import os, json, sys

# One-off live query runner for the RAG assistant.
# Reads API key from OPENAI_API_KEY (or GROQ_API_KEY) environment variable at runtime.

question = os.environ.get("LIVE_QUERY_PROMPT") or "Summarize the knowledge base and list the top 3 document sources."

try:
    # Lazy import runtime dependencies
    from RAG_project.app import load_runtime_dependencies
    from RAG_project.chains.rag_chain import RAGChain
except Exception as e:
    print(json.dumps({"error": "import_error", "message": str(e)}))
    sys.exit(2)

try:
    retriever = load_runtime_dependencies()
    rag = RAGChain(retriever)
    result = rag.ask(question)
    print(json.dumps({"success": True, "question": question, "result": result}, ensure_ascii=False))
except Exception as e:
    import traceback
    tb = traceback.format_exc()
    print(json.dumps({"success": False, "error": str(e), "traceback": tb}))
    # Re-raise to surface non-zero exit code
    raise
