"""
Streamlit UI for the Research Paper RAG project.

Wires together the existing pipeline:
    PDFLoader + WebLoader -> ChunkCleaner -> TextSplitter -> ChunkCleaner (filter/merge)
    -> EmbeddingModel -> FAISSVectorStore -> HybridRetriever (BM25 + FAISS + RRF + Cross-Encoder)
    -> RAGChain (conversation memory + query rewriting + Groq)

Run with:
    streamlit run streamlit_app.py
"""

import sys
from pathlib import Path

# Ensure the package root is on PYTHONPATH when the app is launched
# from the RAG_project folder directly.
sys.path.append(str(Path(__file__).resolve().parent.parent))

import json
import time
import shutil
from datetime import datetime

import streamlit as st

from config import CHUNK_SIZE, CHUNK_OVERLAP, TOP_K
from loaders.pdf_loader import PDFLoader
from loaders.web_loader import WebLoader
from chunking.text_splitter import TextSplitter
from preprocessing.chunk_cleaner import ChunkCleaner
from vectorstore.faiss_db import FAISSVectorStore
from retriever.hybrid import HybridRetriever
from chains.rag_chain import RAGChain
from utils.singletons import get_embedding_model


# ==========================================================
# Page config + styling
# ==========================================================
st.set_page_config(
    page_title="Research Paper RAG",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .stChatMessage { border-radius: 12px; }
    .metric-card {
        background: rgba(127,127,127,0.08);
        border-radius: 10px;
        padding: 0.75rem 1rem;
        margin-bottom: 0.5rem;
    }
    .source-chip {
        display: inline-block;
        padding: 2px 10px;
        margin: 2px 4px 2px 0;
        border-radius: 999px;
        background: rgba(99,102,241,0.15);
        font-size: 0.8rem;
    }
    .app-title {
        font-size: 2rem;
        font-weight: 700;
        margin-bottom: 0;
    }
    .app-subtitle {
        color: rgba(150,150,150,0.9);
        margin-top: 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ==========================================================
# Session state
# ==========================================================
DEFAULT_STATE = {
    "index_built": False,
    "hybrid_retriever": None,
    "rag": None,
    "chat_history": [],       # list of {role, content, sources, retrieval, elapsed}
    "build_metrics": {},      # pages/chunks/vectors/timings from last build
    "uploaded_names": [],
    "url_list": [],
    "show_diagnostics": True,
    "top_k": TOP_K,
    "candidate_pool": 10,
    "rrf_k": 60,
}


def init_state():
    for key, value in DEFAULT_STATE.items():
        if key not in st.session_state:
            # copy mutable defaults so sessions don't share the same list/dict
            st.session_state[key] = value.copy() if isinstance(value, (list, dict)) else value


def reset_state():
    for key, value in DEFAULT_STATE.items():
        st.session_state[key] = value.copy() if isinstance(value, (list, dict)) else value


init_state()

UPLOAD_DIR = Path("streamlit_uploads")


# ==========================================================
# Pipeline builder
# ==========================================================
def build_pipeline(uploaded_files, url_text, top_k, candidate_pool, rrf_k):
    """Runs the full ingestion pipeline on uploaded PDFs + pasted URLs
    and builds the hybrid retriever + RAGChain, storing results in
    session_state."""

    timings = {}
    t_total_start = time.time()

    # 1. Save uploads to disk so PDFLoader can read them the same way
    #    it reads any other folder of PDFs.
    if UPLOAD_DIR.exists():
        shutil.rmtree(UPLOAD_DIR)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    for uploaded_file in uploaded_files:
        target_path = UPLOAD_DIR / uploaded_file.name
        with open(target_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

    # 2. Load PDFs
    t0 = time.time()
    pdf_loader = PDFLoader(str(UPLOAD_DIR))
    pdf_documents = pdf_loader.load_all_pdfs() if uploaded_files else []
    timings["load_pdfs"] = time.time() - t0
    pdf_pages_loaded = len(pdf_documents)

    # 3. Load websites (one URL per line, pasted in the sidebar)
    t0 = time.time()
    urls = [u.strip() for u in url_text.splitlines() if u.strip()]
    web_documents = WebLoader(urls=urls).load_all_urls() if urls else []
    timings["load_web"] = time.time() - t0
    web_pages_loaded = len(web_documents)

    documents = pdf_documents + web_documents

    if not documents:
        if urls and not uploaded_files:
            raise ValueError(
                f"None of the {len(urls)} URL(s) could be loaded — they either "
                f"blocked the request (403/bot protection) or returned no "
                f"extractable text. Check the terminal logs for the specific "
                f"reason per URL. Try a different site, or upload a PDF instead."
            )
        raise ValueError("No PDFs uploaded and no URLs provided — nothing to index.")

    # 4. Clean pages
    t0 = time.time()
    cleaner = ChunkCleaner()
    documents = cleaner.clean_documents(documents)
    timings["clean_pages"] = time.time() - t0
    pages_after_cleaning = len(documents)

    # 5. Split into chunks
    t0 = time.time()
    splitter = TextSplitter()
    chunks = splitter.split_documents(documents)
    timings["split_chunks"] = time.time() - t0
    chunks_created = len(chunks)

    # 6. Filter + merge low quality chunks
    t0 = time.time()
    chunks = cleaner.filter_and_merge(chunks)
    timings["filter_merge"] = time.time() - t0
    chunks_after_filter = len(chunks)

    if not chunks:
        raise ValueError(
            "No usable chunks were produced from the uploaded PDF(s)/URL(s). "
            "Try different sources or check that they contain extractable text."
        )

    # 7. Embed chunks — singleton, so re-clicking "Build Index" across
    #    sessions never reloads the SentenceTransformer from disk again.
    t0 = time.time()
    embedder = get_embedding_model()
    chunks, embeddings = embedder.embed_documents(chunks)
    timings["embed_chunks"] = time.time() - t0

    # 8. Build + persist FAISS index
    t0 = time.time()
    vector_db = FAISSVectorStore()
    vector_db.build_index(embeddings, chunks)
    vector_db.save()
    timings["build_faiss"] = time.time() - t0

    # 9. Build hybrid retriever (BM25 + FAISS + RRF + Cross-Encoder)
    t0 = time.time()
    hybrid_retriever = HybridRetriever(chunks, rrf_k=rrf_k)
    timings["build_hybrid_retriever"] = time.time() - t0

    # 10. Build RAGChain, injecting the hybrid retriever
    t0 = time.time()
    rag = RAGChain(retriever=hybrid_retriever)
    timings["init_rag_chain"] = time.time() - t0

    timings["total"] = time.time() - t_total_start

    metrics = {
        "pdf_pages_loaded": pdf_pages_loaded,
        "web_pages_loaded": web_pages_loaded,
        "pages_after_cleaning": pages_after_cleaning,
        "chunks_created": chunks_created,
        "chunks_after_filter": chunks_after_filter,
        "embedding_dim": embedder.embedding_dim,
        "total_vectors": vector_db.index.ntotal,
        "timings": timings,
        "built_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    return hybrid_retriever, rag, metrics


# ==========================================================
# Sidebar
# ==========================================================
with st.sidebar:
    st.markdown("### 📚 Research Paper RAG")
    st.caption("Hybrid retrieval (FAISS + BM25) with cross-encoder reranking")

    st.divider()
    st.markdown("#### 📄 Upload PDFs")
    uploaded_files = st.file_uploader(
        "Drag and drop one or more research papers",
        type=["pdf"],
        accept_multiple_files=True,
    )

    st.markdown("#### 🌐 Add Websites")
    url_text = st.text_area(
        "Paste one URL per line",
        placeholder="https://arxiv.org/abs/2210.03629\nhttps://example.com/article",
        height=100,
        key="url_text_input",
    )

    has_sources = bool(uploaded_files) or bool(url_text.strip())

    build_col, clear_col = st.columns(2)
    with build_col:
        build_clicked = st.button(
            "🔨 Build Index",
            use_container_width=True,
            type="primary",
            disabled=not has_sources,
        )
    with clear_col:
        reset_clicked = st.button("🗑️ Reset", use_container_width=True)

    if reset_clicked:
        reset_state()
        st.rerun()

    st.divider()

    with st.expander("⚙️ Settings", expanded=False):
        st.session_state["top_k"] = st.slider(
            "Chunks sent to LLM (top_k)", min_value=2, max_value=10,
            value=st.session_state["top_k"],
        )
        st.session_state["candidate_pool"] = st.slider(
            "Candidate pool per retriever (FAISS/BM25)", min_value=5, max_value=30,
            value=st.session_state["candidate_pool"],
        )
        st.session_state["rrf_k"] = st.slider(
            "RRF damping constant (k)", min_value=10, max_value=100,
            value=st.session_state["rrf_k"], step=5,
        )
        st.session_state["show_diagnostics"] = st.checkbox(
            "Show retrieval diagnostics", value=st.session_state["show_diagnostics"]
        )
        st.caption(
            "Changing top_k / candidate_pool / RRF k applies on the **next query** "
            "without needing to rebuild the index."
        )

    if st.session_state["build_metrics"]:
        with st.expander("📈 Performance Metrics", expanded=False):
            m = st.session_state["build_metrics"]
            st.markdown(f"**Built:** {m['built_at']}")
            st.markdown(
                f"""
                <div class="metric-card">📄 PDF pages loaded: <b>{m['pdf_pages_loaded']}</b></div>
                <div class="metric-card">🌐 Web pages loaded: <b>{m['web_pages_loaded']}</b></div>
                <div class="metric-card">🧹 Pages after cleaning: <b>{m['pages_after_cleaning']}</b></div>
                <div class="metric-card">✂️ Chunks created: <b>{m['chunks_created']}</b></div>
                <div class="metric-card">✅ Chunks after filter/merge: <b>{m['chunks_after_filter']}</b></div>
                <div class="metric-card">🧬 Embedding dimension: <b>{m['embedding_dim']}</b></div>
                <div class="metric-card">🗂️ Total vectors indexed: <b>{m['total_vectors']}</b></div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown("**Stage timings (seconds)**")
            for stage, secs in m["timings"].items():
                st.progress(min(secs / max(m["timings"]["total"], 0.001), 1.0), text=f"{stage}: {secs:.2f}s")

    st.divider()

    export_col, clear_chat_col = st.columns(2)
    with export_col:
        if st.session_state["chat_history"]:
            chat_json = json.dumps(st.session_state["chat_history"], indent=2, default=str)
            st.download_button(
                "⬇️ Export Chat",
                data=chat_json,
                file_name=f"chat_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
                use_container_width=True,
            )
        else:
            st.button("⬇️ Export Chat", disabled=True, use_container_width=True)
    with clear_chat_col:
        if st.button("🧹 Clear Chat", use_container_width=True, disabled=not st.session_state["chat_history"]):
            st.session_state["chat_history"] = []
            if st.session_state["rag"] is not None:
                st.session_state["rag"].memory.clear()
            st.rerun()


# ==========================================================
# Build index on click
# ==========================================================
if build_clicked and has_sources:
    with st.status("Building retrieval pipeline...", expanded=True) as status:
        try:
            st.write("📄 Loading and cleaning PDFs...")
            st.write("🌐 Fetching and extracting websites...")
            st.write("✂️ Chunking documents...")
            st.write("🧬 Embedding chunks...")
            st.write("🗂️ Building FAISS + BM25 hybrid index...")

            hybrid_retriever, rag, metrics = build_pipeline(
                uploaded_files or [],
                url_text,
                st.session_state["top_k"],
                st.session_state["candidate_pool"],
                st.session_state["rrf_k"],
            )

            url_list = [u.strip() for u in url_text.splitlines() if u.strip()]

            st.session_state["hybrid_retriever"] = hybrid_retriever
            st.session_state["rag"] = rag
            st.session_state["build_metrics"] = metrics
            st.session_state["index_built"] = True
            st.session_state["uploaded_names"] = [f.name for f in (uploaded_files or [])]
            st.session_state["url_list"] = url_list
            st.session_state["chat_history"] = []

            status.update(label="✅ Index built successfully!", state="complete")
        except Exception as e:
            status.update(label="❌ Build failed", state="error")
            st.error(f"Error building pipeline: {e}")


# ==========================================================
# Main area — header
# ==========================================================
st.markdown('<p class="app-title">Chat with your research papers</p>', unsafe_allow_html=True)
source_chips = "".join(
    f'<span class="source-chip">📄 {name}</span>' for name in st.session_state["uploaded_names"]
) + "".join(
    f'<span class="source-chip">🌐 {url}</span>' for url in st.session_state["url_list"]
)
if source_chips:
    st.markdown(f'<p class="app-subtitle">{source_chips}</p>', unsafe_allow_html=True)
else:
    st.markdown(
        '<p class="app-subtitle">Upload PDFs and/or paste URLs on the left, then build the index to start chatting.</p>',
        unsafe_allow_html=True,
    )

st.divider()


# ==========================================================
# Chat rendering
# ==========================================================
def render_sources(sources):
    if not sources:
        return
    chips = "".join(f'<span class="source-chip">📎 {s}</span>' for s in sources)
    st.markdown(chips, unsafe_allow_html=True)


def render_diagnostics(retrieval):
    """Final reranked results (what actually went into the prompt)."""
    if not retrieval:
        return
    with st.expander(f"🔍 Final retrieved context ({len(retrieval)} chunks)"):
        for i, r in enumerate(retrieval, start=1):
            doc = r.get("document") if isinstance(r, dict) else r
            rrf = r.get("rrf_score") if isinstance(r, dict) else None
            rerank = r.get("rerank_score") if isinstance(r, dict) else None
            chunk_id = doc.metadata.get("chunk_id", "unknown") if doc else "unknown"
            page = doc.metadata.get("page", "?") if doc else "?"
            source = doc.metadata.get("source", "?") if doc else "?"

            score_bits = []
            if rrf is not None:
                score_bits.append(f"RRF: {rrf:.4f}")
            if rerank is not None:
                score_bits.append(f"Rerank: {rerank:.4f}")
            score_str = " · ".join(score_bits) if score_bits else "n/a"

            st.markdown(f"**{i}. `{chunk_id}`** — {source} (page {page}) — {score_str}")
            if doc:
                preview = doc.page_content[:300].replace("\n", " ")
                st.caption(preview + ("..." if len(doc.page_content) > 300 else ""))
            st.markdown("---")


def render_pipeline_debug():
    """Stage-by-stage FAISS / BM25 / RRF / Cross-Encoder breakdown for
    the LAST query — reads HybridRetriever.last_debug, same data the
    CLI's DEBUG=True mode prints, just rendered as UI tables."""
    hybrid_retriever = st.session_state.get("hybrid_retriever")
    debug_info = getattr(hybrid_retriever, "last_debug", None) if hybrid_retriever else None
    if not debug_info:
        return

    def _page(doc):
        return doc.metadata.get("page", "?") if isinstance(doc, object) and hasattr(doc, "metadata") else "?"

    with st.expander("🧪 Retrieval pipeline breakdown (FAISS / BM25 / RRF / Cross-Encoder)"):
        faiss_col, bm25_col = st.columns(2)

        with faiss_col:
            st.markdown("**FAISS**")
            for r in debug_info.get("faiss_results", []):
                doc = r.get("document", r) if isinstance(r, dict) else r
                score = doc.metadata.get("score", "?") if hasattr(doc, "metadata") else "?"
                st.text(f"Page {_page(doc)}   {score}")

        with bm25_col:
            st.markdown("**BM25**")
            for r in debug_info.get("bm25_results", []):
                doc = r.get("document", r) if isinstance(r, dict) else r
                score = r.get("score", "?") if isinstance(r, dict) else "?"
                st.text(f"Page {_page(doc)}   {score}")

        rrf_col, ce_col = st.columns(2)

        with rrf_col:
            st.markdown("**RRF**")
            for r in debug_info.get("rrf_results", []):
                doc = r.get("document", r)
                score = r.get("rrf_score", "?")
                score_str = f"{score:.4f}" if isinstance(score, float) else str(score)
                st.text(f"Page {_page(doc)}   {score_str}")

        with ce_col:
            st.markdown("**Cross Encoder**")
            for r in debug_info.get("cross_encoder_results", []):
                doc = r.get("document", r)
                score = r.get("rerank_score", "?")
                score_str = f"{score:.2f}" if isinstance(score, float) else str(score)
                st.text(f"Page {_page(doc)}   Score: {score_str}")


for message in st.session_state["chat_history"]:
    with st.chat_message(message["role"]):
        st.write(message["content"])
        if message["role"] == "assistant":
            render_sources(message.get("sources"))
            if st.session_state["show_diagnostics"]:
                render_diagnostics(message.get("retrieval"))
            if message.get("elapsed") is not None:
                st.caption(f"⏱️ Answered in {message['elapsed']:.2f}s")


# ==========================================================
# Chat input
# ==========================================================
prompt_disabled = not st.session_state["index_built"]
user_question = st.chat_input(
    "Ask a question about your papers..." if not prompt_disabled else "Build the index first →",
    disabled=prompt_disabled,
)

if user_question:
    st.session_state["chat_history"].append({"role": "user", "content": user_question})
    with st.chat_message("user"):
        st.write(user_question)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                t0 = time.time()
                # keep the injected retriever's rrf_k in sync with the
                # sidebar setting for this query
                st.session_state["hybrid_retriever"].rrf_k = st.session_state["rrf_k"]

                response = st.session_state["rag"].ask(user_question)
                elapsed = time.time() - t0

                answer = response["answer"]
                sources = response.get("sources", [])
                retrieval = response.get("retrieval", [])

                st.write(answer)
                render_sources(sources)
                if st.session_state["show_diagnostics"]:
                    render_diagnostics(retrieval)
                    render_pipeline_debug()
                st.caption(f"⏱️ Answered in {elapsed:.2f}s")

                if response.get("rewritten_question") and response["rewritten_question"] != user_question:
                    with st.expander("✏️ Rewritten query (used for retrieval)"):
                        st.write(response["rewritten_question"])

                st.session_state["chat_history"].append(
                    {
                        "role": "assistant",
                        "content": answer,
                        "sources": sources,
                        "retrieval": retrieval,
                        "elapsed": elapsed,
                    }
                )
            except Exception as e:
                st.error(f"Error: {e}")