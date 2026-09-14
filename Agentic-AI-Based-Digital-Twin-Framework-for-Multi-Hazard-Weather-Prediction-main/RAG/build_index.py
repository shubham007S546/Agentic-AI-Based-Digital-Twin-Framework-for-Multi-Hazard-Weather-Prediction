"""
build_index.py
---------------
WORKFLOW 1 — Offline index building.

Run this explicitly whenever the source PDFs change:

    python build_index.py

Responsibilities:
    • Load PDFs
    • Clean pages
    • Split into chunks
    • Filter/merge chunks
    • Generate embeddings
    • Build + save FAISS index
    • Save processed chunks (so BM25 can be rebuilt at runtime from the
      EXACT same chunk list, without touching PDFs or embeddings again)

app.py NEVER performs any of the above — it only loads what this
script produces. This is the fix for the "entire index rebuilt every
run" inefficiency.
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

from config import PDF_DIR, WEB_URLS, WEB_URLS_FILE
from loaders.pdf_loader import PDFLoader
from loaders.web_loader import WebLoader
from loaders.project_loader import ProjectLoader
from chunking.text_splitter import TextSplitter
from preprocessing.chunk_cleaner import ChunkCleaner
from vectorstore.faiss_db import FAISSVectorStore
from utils.singletons import get_embedding_model
from utils.logger import logger


def build_index():
    logger.info("Starting offline index build...")

    # Load PDFs from the configured PDF folder
    pdf_loader = PDFLoader(PDF_DIR)
    pdf_documents = pdf_loader.load_all_pdfs()
    print(f"Pages Loaded (PDF) : {len(pdf_documents)}")

    # Load websites (optional)
    web_loader = WebLoader(urls=WEB_URLS, url_file=WEB_URLS_FILE)
    web_documents = web_loader.load_all_urls()
    print(f"Pages Loaded (Web) : {len(web_documents)}")

    # Load project documentation (README, architecture, guides, schemas)
    repo_root = Path(__file__).resolve().parent.parent
    project_loader = ProjectLoader(repo_root)
    project_documents = project_loader.load_project_docs()
    print(f"Docs Loaded (Project) : {len(project_documents)}")

    documents = pdf_documents + web_documents + project_documents
    print(f"Total Pages/Docs Loaded : {len(documents)}")

    # Clean pages: strip boilerplate, URLs, page numbers, front matter,
    # repeated headers/footers BEFORE splitting
    cleaner = ChunkCleaner()
    documents = cleaner.clean_documents(documents)
    print(f"Pages Remaining After Cleaning : {len(documents)}")

    # Split into chunks
    splitter = TextSplitter()
    chunks = splitter.split_documents(documents)
    print(f"Chunks Created : {len(chunks)}")

    # Drop low-quality chunks, merge tiny ones into same-page neighbors
    chunks = cleaner.filter_and_merge(chunks)
    print(f"Chunks Remaining After Filter + Merge : {len(chunks)}")

    if chunks:
        print("\nFirst Chunk Metadata:")
        print(chunks[0].metadata)
        print("\nFirst Chunk:")
        print(chunks[0].page_content[:500])

    # Embed chunks. embed_documents returns (valid_chunks, embeddings) —
    # some chunks may get dropped if they end up empty, so `chunks` is
    # reassigned to stay aligned 1:1 with `embeddings`.
    embedder = get_embedding_model()
    chunks, embeddings = embedder.embed_documents(chunks)
    print(f"\nChunks Embedded : {len(chunks)}")
    print(f"Embedding Shape : {embeddings.shape}")
    print(f"Embedding Dimension : {embedder.embedding_dim}")

    # Build FAISS vector index and persist it to disk
    vector_db = FAISSVectorStore()
    vector_db.build_index(embeddings, chunks)
    vector_db.save()
    print("\nVector Database Created")
    print("Total Vectors :", vector_db.index.ntotal)
    # Note: vector_db.save() already persists the chunks alongside the
    # index (VECTOR_DB_DIR / "documents.pkl"), so app.py can load both
    # the index and the exact chunk list from a single vector_db.load()
    # call — no separate chunks file needed.

    logger.info("Index build complete.")


if __name__ == "__main__":
    build_index()