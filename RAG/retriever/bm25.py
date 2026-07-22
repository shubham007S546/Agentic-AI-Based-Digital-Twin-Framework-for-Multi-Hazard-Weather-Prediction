import re
import numpy as np
from rank_bm25 import BM25Okapi


def tokenize(text: str):
    return re.findall(r"\b\w+\b", text.lower())


class BM25Retriever:

    def __init__(self):
        self.documents = []
        self.bm25 = None

    def build(self, documents):
        self.documents = documents
        tokenized = [tokenize(doc.page_content) for doc in documents]
        self.bm25 = BM25Okapi(tokenized)

    def search(self, query, top_k=4):
        query_tokens = tokenize(query)
        scores = self.bm25.get_scores(query_tokens)
        indices = np.argsort(scores)[::-1][:top_k]

        results = []
        for rank, idx in enumerate(indices, start=1):
            results.append({
                "rank": rank,
                "score": float(scores[idx]),
                "document": self.documents[idx],
            })
        return results