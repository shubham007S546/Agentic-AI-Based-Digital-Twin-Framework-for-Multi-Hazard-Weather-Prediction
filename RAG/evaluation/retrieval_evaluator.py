"""
Evaluate Retrieval Quality
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from retriever.retriever import Retriever


class RetrievalEvaluator:

    def __init__(self):

        self.retriever = Retriever()

    def evaluate(
        self,
        question,
        top_k=4
    ):

        print("=" * 100)
        print(f"QUESTION:\n{question}")
        print("=" * 100)

        results = self.retriever.retrieve(
            question,
            top_k=top_k
        )

        for rank, doc in enumerate(results, start=1):

            score = doc.metadata.get("score")

            print()

            print("-" * 80)

            print(f"Rank   : {rank}")

            if score is not None:
                print(f"Score  : {score:.4f}")

            print(f"Source : {doc.metadata['source']}")

            print(f"Page   : {doc.metadata['page']}")

            print()

            preview = doc.page_content[:600]

            print(preview)

            print()

        return results