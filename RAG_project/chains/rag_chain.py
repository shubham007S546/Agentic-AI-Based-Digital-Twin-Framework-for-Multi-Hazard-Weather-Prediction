"""
RAG Chain
---------
Coordinates the complete RAG pipeline, including conversation memory,
history-aware query rewriting, and (when DEBUG=True) full retrieval
pipeline logging.
"""

import sys
import re
import time
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from retriever.retriever import Retriever
from prompts.rag_prompt import RAGPrompt
from memory.conversation_memory import ConversationMemory
from query.query_rewritter import QueryRewriter
from config import TOP_K, DEBUG
from utils.singletons import get_llm
from utils.logger import logger


# Small talk never needs retrieval — running it through the strict
# "answer ONLY from context" pipeline is what caused "thanks" to return
# "I couldn't find this information in the uploaded papers." Catching
# it here also skips the embedding/BM25/rerank/LLM round trip entirely,
# so these turns answer instantly instead of taking 15-20s.
_THANKS = {"thanks", "thank you", "thankyou", "thx", "ty", "cheers", "appreciate it", "much appreciated"}
_GREETINGS = {"hi", "hello", "hey", "yo", "hiya"}
_GOODBYES = {"bye", "goodbye", "see ya", "see you", "later", "cya"}
_ACKS = {"ok", "okay", "k", "cool", "great", "awesome", "nice", "good", "perfect",
         "got it", "sounds good", "sure", "alright", "fine"}


class RAGChain:

    def __init__(self, retriever=None):
        logger.info("Initializing RAG Pipeline...")

        # Accept an injected retriever (e.g. HybridRetriever) so the
        # same chain can run plain vector search OR hybrid+rerank
        # without duplicating pipeline code. Falls back to plain
        # Retriever if nothing is passed in, so old callers still work.
        self.retriever = retriever if retriever is not None else Retriever()

        # Singleton — loaded once, reused across every RAGChain/QueryRewriter.
        self.llm = get_llm()
        self.memory = ConversationMemory()
        self.query_rewriter = QueryRewriter()

        logger.info("RAG Pipeline Ready.")

    @staticmethod
    def _chitchat_reply(question: str):
        """Returns a canned reply for pure small talk, or None if the
        message should go through the real retrieval pipeline."""
        normalized = re.sub(r"[^\w\s]", "", question.strip().lower())

        if normalized in _THANKS:
            return "You're welcome! Let me know if you have more questions about the papers."
        if normalized in _GREETINGS:
            return "Hi! Ask me anything about the uploaded research papers."
        if normalized in _GOODBYES:
            return "Goodbye! Come back anytime you have more questions about the papers."
        if normalized in _ACKS:
            return "Got it — let me know if you'd like to dig into anything else from the papers."
        return None

    # ------------------------------------------------------------------
    # Debug printing — only ever called when DEBUG=True. Reads whatever
    # HybridRetriever stashed on `self.retriever.last_debug`; degrades
    # gracefully (empty sections) if a plain Retriever without that
    # attribute is injected instead.
    # ------------------------------------------------------------------
    @staticmethod
    def _page(doc):
        metadata = doc.get("metadata", {}) if isinstance(doc, dict) else getattr(doc, "metadata", {})
        return metadata.get("page", "?")

    def _print_section(self, title):
        print(f"\n===== {title} =====")

    def _print_faiss(self, results):
        # FAISS results are raw documents with metadata["score"] attached
        # by FAISSVectorStore.search() (L2 distance).
        self._print_section("FAISS")
        for r in results:
            doc = r.get("document", r) if isinstance(r, dict) else r
            metadata = doc.get("metadata", {}) if isinstance(doc, dict) else getattr(doc, "metadata", {})
            print(f"Page {metadata.get('page', '?')}   {metadata.get('score', '?')}")

    def _print_bm25(self, results):
        self._print_section("BM25")
        for r in results:
            doc = r.get("document", r) if isinstance(r, dict) else r
            page = self._page(doc)
            score = r.get("score", "?") if isinstance(r, dict) else "?"
            print(f"Page {page}   {score}")

    def _print_rrf(self, results):
        self._print_section("RRF")
        for r in results:
            page = self._page(r.get("document", r))
            print(f"Page {page}   {r.get('rrf_score', '?'):.4f}" if isinstance(r.get("rrf_score"), float)
                  else f"Page {page}   {r.get('rrf_score', '?')}")

    def _print_cross_encoder(self, results):
        self._print_section("Cross Encoder")
        for r in results:
            page = self._page(r.get("document", r))
            score = r.get("rerank_score", "?")
            score_str = f"{score:.2f}" if isinstance(score, float) else str(score)
            print(f"Page {page}   Score: {score_str}")

    def _print_debug(self, question, rewritten_question, conversation, final_prompt):
        self._print_section("Original Question")
        print(question)

        self._print_section("Rewritten Question")
        print(rewritten_question)

        self._print_section("Conversation History")
        print(conversation if conversation else "(empty)")

        debug_info = getattr(self.retriever, "last_debug", {})

        self._print_faiss(debug_info.get("faiss_results", []))
        self._print_bm25(debug_info.get("bm25_results", []))
        self._print_rrf(debug_info.get("rrf_results", []))
        self._print_cross_encoder(debug_info.get("cross_encoder_results", []))

        self._print_section("Final Retrieved Context")
        print(final_prompt)

    def ask(self, question: str):

        t_start = time.perf_counter()

        # Step 0: Record the user's question in memory
        self.memory.add_user_message(question)

        # Chitchat ("thanks", "hi", "ok"...) never needs retrieval.
        # Answer directly and skip rewriting/search/LLM entirely.
        chitchat_reply = self._chitchat_reply(question)
        if chitchat_reply is not None:
            self.memory.add_assistant_message(chitchat_reply)
            logger.info(
                "ask() timing (chitchat)",
                total=f"{time.perf_counter() - t_start:.2f}s"
            )
            return {
                "question": question,
                "rewritten_question": question,
                "answer": chitchat_reply,
                "sources": [],
                "retrieval": []
            }

        # Step 1: Get conversation history so far
        conversation = self.memory.get_context()

        # Step 2: Rewrite the question into a standalone question
        # using conversation history (resolves "it", "why", "that", etc.)
        t0 = time.perf_counter()
        rewritten_question = self.query_rewriter.rewrite(
            question,
            conversation
        )
        t_rewrite = time.perf_counter() - t0

        # Step 3: Retrieve using the REWRITTEN question, not the raw one.
        # This is usually the most expensive step (query embedding +
        # FAISS/BM25 search + cross-encoder reranking all happen inside
        # self.retriever.retrieve()).
        t0 = time.perf_counter()
        retrieved_results = self.retriever.retrieve(
            rewritten_question,
            top_k=TOP_K
        )
        t_retrieve = time.perf_counter() - t0

        # Step 4: Build Prompt — the ORIGINAL question is shown to the
        # user/LLM here, not the rewritten one, so the answer still
        # addresses what the user actually typed
        t0 = time.perf_counter()
        prompt, sources = RAGPrompt.build(
            question,
            retrieved_results,
            conversation
        )
        t_prompt = time.perf_counter() - t0

        # All debug output is gated behind a single flag. When
        # DEBUG=False, none of this runs and there is zero extra output.
        if DEBUG:
            self._print_debug(question, rewritten_question, conversation, prompt)

        # Step 5: Generate Answer
        t0 = time.perf_counter()
        answer = self.llm.generate(prompt)
        t_generate = time.perf_counter() - t0

        # Step 6: Record the assistant's answer in memory
        self.memory.add_assistant_message(answer)

        t_total = time.perf_counter() - t_start

        # Per-stage timing so slow queries can be diagnosed from logs
        # instead of guessed at. rewrite = query_rewriter LLM call,
        # retrieve = embedding + FAISS/BM25 + cross-encoder rerank,
        # prompt = pure string building (should be ~0), generate = LLM call.
        logger.info(
            "ask() timing",
            rewrite=f"{t_rewrite:.2f}s",
            retrieve=f"{t_retrieve:.2f}s",
            prompt_build=f"{t_prompt:.2f}s",
            generate=f"{t_generate:.2f}s",
            total=f"{t_total:.2f}s",
        )

        return {
            "question": question,
            "rewritten_question": rewritten_question,
            "answer": answer,
            "sources": sources,
            "retrieval": retrieved_results
        }