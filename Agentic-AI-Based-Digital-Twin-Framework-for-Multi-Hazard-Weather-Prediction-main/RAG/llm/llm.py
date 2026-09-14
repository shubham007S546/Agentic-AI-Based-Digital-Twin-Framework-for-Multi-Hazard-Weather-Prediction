import os
import sys
from pathlib import Path

from dotenv import load_dotenv
try:
    from groq import Groq
    _HAS_GROQ = True
except ImportError:
    from openai import OpenAI
    _HAS_GROQ = False

# Ensure the RAG package can import from its own package root when the backend
# starts from a different working directory.
PACKAGE_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PACKAGE_ROOT))

# Load environment variables from repo root .env, RAG .env, or find_dotenv.
for candidate in [PACKAGE_ROOT.parent / '.env', PACKAGE_ROOT / '.env']:
    if candidate.exists():
        load_dotenv(candidate)
load_dotenv()

from config import (
    LLM_MODEL,
    TEMPERATURE,
    MAX_OUTPUT_TOKENS,
    TOP_P
)

from utils.logger import logger


class GroqLLM:
    """
    Calls Groq's high-speed LPU inference API using the official `groq` SDK
    (or OpenAI-compatible fallback).
    """

    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")

        self._fallback = not api_key
        if self._fallback:
            logger.warning(
                "GROQ_API_KEY not configured; using the local extractive RAG fallback."
            )
            self.client = None
            return

        self.model = os.getenv("GROQ_MODEL", LLM_MODEL)
        logger.info(f"Initializing GroqLLM with model: {self.model}")

        if _HAS_GROQ:
            self.client = Groq(api_key=api_key)
        else:
            self.client = OpenAI(
                api_key=api_key,
                base_url="https://api.groq.com/openai/v1"
            )

        logger.info("Groq Loaded successfully")

    def generate(self, prompt: str) -> str:
        if self._fallback or not self.client:
            context = prompt.split("Context:", 1)[-1].strip()
            if not context:
                return "No hosted language model is configured. Add GROQ_API_KEY for generated answers."
            excerpt = " ".join(context.split())[:1200]
            return (
                "A hosted language model is not configured, so this is a local "
                f"extractive answer from the retrieved context:\n\n{excerpt}"
            )

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=TEMPERATURE,
            max_tokens=MAX_OUTPUT_TOKENS,
            top_p=TOP_P
        )

        return response.choices[0].message.content.strip()