import os, json, traceback, sys

question = os.environ.get("LIVE_QUERY_PROMPT") or "Summarize the knowledge base and list the top 3 document sources."

# No try/except here — allow full traceback to show for debugging
from RAG_project.app import load_runtime_dependencies
from RAG_project.chains.rag_chain import RAGChain

retriever = load_runtime_dependencies()
rag = RAGChain(retriever)
result = rag.ask(question)
print(json.dumps({"success": True, "question": question, "result": result}, ensure_ascii=False))
