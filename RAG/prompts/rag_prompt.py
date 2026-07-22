"""
Professional Prompt Builder
"""


class RAGPrompt:

    @staticmethod
    def _unwrap(result):
        """
        retrieved_results can be either:
          - raw Document objects (plain Retriever -> FAISSVectorStore.search)
          - dicts like {"document": Document, "rrf_score":..., "rerank_score":...}
            (HybridRetriever -> Reranker.rerank)
        Normalize to the underlying Document either way.
        """
        if isinstance(result, dict):
            return result["document"]
        return result

    @staticmethod
    def build(question: str, retrieved_results, conversation_history: str = ""):

        context = []

        sources = []

        for result in retrieved_results:

            doc = RAGPrompt._unwrap(result)

            metadata = doc.metadata

            source = metadata.get("source", "Unknown source")
            # No fake "N/A" — a page number only exists for paginated
            # sources (PDFs). Code/markdown/config files use a line
            # number instead, if the collector recorded one. If
            # neither is present, we simply omit that line rather than
            # printing a placeholder.
            page = metadata.get("page")
            line = metadata.get("line")

            score = metadata.get("score")
            score_line = f"Similarity Score : {score:.4f}\n" if score is not None else ""

            location_line = ""
            location_suffix = ""
            if page is not None:
                location_line = f"Page   : {page}\n"
                location_suffix = f" (Page {page})"
            elif line is not None:
                location_line = f"Line   : {line}\n"
                location_suffix = f" (Line {line})"

            context.append(
                f"""
Source : {source}
{location_line}{score_line}
Content:
{doc.page_content}
"""
            )

            sources.append(f"{source}{location_suffix}")

        context = "\n\n" + ("\n" + "=" * 80 + "\n").join(context)

        prompt = f"""
You are an expert AI Research Assistant.

You MUST answer using ONLY the retrieved context below. This is a
strict constraint, not a preference.

Instructions:

1. Use ONLY the retrieved context. Do NOT use outside knowledge, even
   if you are confident it is correct or well-known in the field.
2. Do NOT fill gaps, add explanations, examples, or comparisons that
   are not explicitly stated in the retrieved context — even standard
   machine learning knowledge (e.g. general facts about Transformers,
   Linear Regression, or any other technique) must come from the
   context itself, not from what you already know about the topic.
3. If the retrieved context does not contain enough information to
   answer the question, reply EXACTLY with:

"I couldn't find this information in the uploaded papers."

   If the context covers only part of the question, answer only the
   part that is supported and explicitly say the rest was not found
   in the papers. Do not soften or work around this rule.
4. If multiple chunks contain useful information,
combine them into one complete answer, but only using what is stated.
5. Explain in clear language.
6. Mention important technical terms as they appear in the context.
7. At the end include the sources.
================================================

Conversation History

{conversation_history}

================================================
=====================================================

CONTEXT

{context}

=====================================================

QUESTION

{question}

=====================================================

ANSWER
"""

        return prompt, list(set(sources))