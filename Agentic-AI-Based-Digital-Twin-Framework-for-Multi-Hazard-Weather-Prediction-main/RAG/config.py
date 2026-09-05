"""
Global Configuration File
"""

import os
from pathlib import Path

# ==========================================================
# Project Directories
# ==========================================================

BASE_DIR = Path(__file__).resolve().parent

# Root data folder for RAG. Keep this as the project-level data root.
DATA_DIR = BASE_DIR / "data"

# PDF ingestion folder. Put your own PDFs here.
PDF_DIR = Path(os.environ.get("RAG_PDF_DIR", (DATA_DIR / "pdfs") if (DATA_DIR / "pdfs").exists() else DATA_DIR))

# ==========================================================
# Website Sources (optional — mixed in alongside PDFs)
# ==========================================================

# Add URLs directly here...
WEB_URLS = []  # e.g. ["https://arxiv.org/abs/2210.03629"]

# ...or list them one-per-line in data/urls.txt (blank lines and lines
# starting with # are ignored). Both are combined if you use both.
WEB_URLS_FILE = DATA_DIR / "urls.txt"

VECTOR_DB_DIR = BASE_DIR / "database" / "faiss_index"

# Extracted image cache for PDF figures. Keep this out of the PDF source
# folder so the data directory only contains your input documents.
IMAGE_DIR = BASE_DIR.parent / "knowledge_engine" / "cache" / "extracted_images"

LOG_DIR = BASE_DIR / "logs"

# ==========================================================
# Embedding Model
# ==========================================================

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# ==========================================================
# Chunking Configuration
# ==========================================================

CHUNK_SIZE = 1000

CHUNK_OVERLAP = 200

# Remove very small chunks
MIN_CHUNK_SIZE = 150

# ==========================================================
# Retrieval
# ==========================================================

TOP_K = 4

SIMILARITY_THRESHOLD = 0.35

# ==========================================================
# LLM
# ==========================================================

LLM_MODEL = "openai/gpt-oss-120b"  # llama-3.3-70b-versatile was deprecated by Groq; this is its recommended replacement

TEMPERATURE = 0.2

MAX_OUTPUT_TOKENS = 1024

TOP_P = 0.95
# ==========================================================
# PDF Processing
# ==========================================================

SUPPORTED_FILES = [".pdf"]

EXTRACT_IMAGES = True

EXTRACT_TABLES = True

OCR_ENABLED = False

# ==========================================================
# Text Cleaning
# ==========================================================

REMOVE_HEADERS = True

REMOVE_FOOTERS = True

REMOVE_URLS = True

NORMALIZE_WHITESPACE = True

REMOVE_REFERENCES = False

REMOVE_ACKNOWLEDGEMENT = False

# ==========================================================
# Retrieval Debugging
# ==========================================================

# When True, RAGChain prints the full pipeline trace (original/rewritten
# question, conversation history, FAISS/BM25/RRF/CrossEncoder ranks,
# final retrieved context). No output at all when False.
DEBUG = False

# ==========================================================
# Logging
# ==========================================================

LOG_LEVEL = "INFO"