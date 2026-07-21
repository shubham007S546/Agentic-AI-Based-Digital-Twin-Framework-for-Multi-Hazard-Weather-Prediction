from sentence_transformers import CrossEncoder


def _get_page_content(doc):
    """Works whether doc is a Document object or a plain dict."""
    if isinstance(doc, dict):
        return doc.get("page_content", "")
    return getattr(doc, "page_content", "")


class Reranker:

    def __init__(self, model_name="cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model = CrossEncoder(model_name)

    def rerank(self, query, candidates, top_k=4):
        """
        candidates: list of dicts, each with a "document" key
        (as produced by BM25Retriever.search or the hybrid fuser).
        """
        if not candidates:
            return []

        pairs = [(query, _get_page_content(c["document"])) for c in candidates]
        scores = self.model.predict(pairs)

        for c, s in zip(candidates, scores):
            c["rerank_score"] = float(s)

        reranked = sorted(candidates, key=lambda c: c["rerank_score"], reverse=True)
        return reranked[:top_k]