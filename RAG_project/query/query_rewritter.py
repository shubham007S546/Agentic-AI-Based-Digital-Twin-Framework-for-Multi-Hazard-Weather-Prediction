"""
Query Rewriter
--------------
TRUE history-aware query rewriting — not grammar correction.

Given the running conversation + a new (possibly context-dependent)
question, produces a single standalone retrieval query with every
pronoun and omitted entity resolved. If the question already stands
alone, it's returned unchanged.
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from utils.singletons import get_llm
from utils.logger import logger


class QueryRewriter:

    SYSTEM_PROMPT = """You are a query-rewriting engine for a retrieval system.

Your ONLY job: given a conversation history and a new user question,
rewrite the new question into a fully standalone search query.

Rules:
1. Resolve every pronoun ("it", "they", "this", "that", "he", "she",
   "them") into the actual entity/topic it refers to, using the
   conversation history.
2. Resolve omitted/implied entities (e.g. "Why was it selected?" ->
   "Why was the <specific model/topic from history> selected?").
3. The rewritten query must make sense with ZERO conversation context.
4. NEVER answer the question. Only rewrite it.
5. If the original question is already standalone (no pronouns, no
   missing context), return it EXACTLY as-is, unchanged.
6. Output ONLY the rewritten question — no preamble, no quotes, no
   labels like "Rewritten:", no explanation.

Examples:

History:
User: What is Temporal Fusion Transformer?
Assistant: ...

New question: Why was it selected?
Rewritten question: Why was the Temporal Fusion Transformer selected?

History:
User: Explain Linear Regression.
Assistant: ...

New question: What are its limitations?
Rewritten question: What are the limitations of Linear Regression?

History: (empty)
New question: What is an inclinometer?
Rewritten question: What is an inclinometer?
"""

    def __init__(self, llm=None):
        # Reuse the singleton Gemini client instead of spinning up a new
        # model connection on every rewrite call.
        self.llm = llm if llm is not None else get_llm()

    def rewrite(self, question: str, conversation: str) -> str:
        # No history yet -> nothing to resolve, skip the LLM call entirely.
        if not conversation or not conversation.strip():
            return question.strip()

        prompt = (
            f"{self.SYSTEM_PROMPT}\n\n"
            f"History:\n{conversation}\n\n"
            f"New question: {question}\n"
            f"Rewritten question:"
        )

        try:
            rewritten = self.llm.generate(prompt).strip()
        except Exception as e:
            logger.error(f"Query rewrite failed, falling back to original question: {e}")
            return question.strip()

        # Strip accidental wrapping quotes/labels the LLM might add
        rewritten = rewritten.strip('"').strip()
        if rewritten.lower().startswith("rewritten question:"):
            rewritten = rewritten.split(":", 1)[1].strip()

        return rewritten if rewritten else question.strip()