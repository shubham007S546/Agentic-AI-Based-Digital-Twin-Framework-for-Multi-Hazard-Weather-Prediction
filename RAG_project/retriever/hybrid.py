"""
HybridRetriever
---------------
FAISS + BM25 -> Reciprocal Rank Fusion -> Cross-Encoder rerank.

CHANGES:
    • Reranker is now pulled from the singleton registry instead of
      being constructed fresh every time a HybridRetriever is built
      (Bonus: avoid redundant model loading).
    • retrieve() now stashes every intermediate stage (faiss_results,
      bm25_results, rrf-fused, cross-encoder reranked) on
      `self.last_debug`. RAGChain reads this to print full retrieval
      debug output WITHOUT changing this method's public signature —
      existing callers/APIs are untouched.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from retriever.bm25 import BM25Retriever
from retriever.retriever import Retriever
from utils.singletons import get_reranker


def rrf_score(rank, k=60):
    return 1 / (k + rank)


def _get_metadata(doc):
    """Works whether doc is a Document object or a plain dict."""
    if isinstance(doc, dict):
        return doc.get("metadata", {})
    return getattr(doc, "metadata", {})


class HybridRetriever:

    def __init__(self, documents, rrf_k=60):
        """
        documents: same chunk list used to build the FAISS index,
        so BM25 is built over identical text/metadata (including
        the chunk_id stamped by TextSplitter).
        """
        self.rrf_k = rrf_k

        self.bm25 = BM25Retriever()
        self.bm25.build(documents)

        self.vector_retriever = Retriever()

        # Singleton — loaded once for the whole process, not once per
        # HybridRetriever instance.
        self.reranker = get_reranker()

        # Populated on every retrieve() call. Read by RAGChain when
        # DEBUG=True; ignored (and effectively free) otherwise.
        self.last_debug = {}

    def _fuse(self, faiss_results, bm25_results):
        merged = {}

        for rank, result in enumerate(faiss_results, start=1):
            doc = result["document"] if isinstance(result, dict) else result
            metadata = _get_metadata(doc)
            key = metadata["chunk_id"]

            if key not in merged:
                merged[key] = {"document": doc, "rrf_score": 0}

            merged[key]["rrf_score"] += rrf_score(rank, self.rrf_k)

        for rank, result in enumerate(bm25_results, start=1):
            doc = result["document"]
            metadata = _get_metadata(doc)
            key = metadata["chunk_id"]

            if key not in merged:
                merged[key] = {"document": doc, "rrf_score": 0}

            merged[key]["rrf_score"] += rrf_score(rank, self.rrf_k)

        results = list(merged.values())
        results.sort(key=lambda x: x["rrf_score"], reverse=True)
        return results

    def retrieve(self, query, top_k=4, candidate_pool=10):
        faiss_results = self.vector_retriever.retrieve(query, top_k=candidate_pool)
        bm25_results = self.bm25.search(query, top_k=candidate_pool)

        fused = self._fuse(faiss_results, bm25_results)
        reranked = self.reranker.rerank(query, fused, top_k=top_k)

        # Cheap to always populate; only ever printed when DEBUG=True.
        self.last_debug = {
            "faiss_results": faiss_results,
            "bm25_results": bm25_results,
            "rrf_results": fused,
            "cross_encoder_results": reranked,
        }

        return reranked