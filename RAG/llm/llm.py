import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# Ensure the RAG package can import from its own package root when the backend
# starts from a different working directory.
PACKAGE_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PACKAGE_ROOT))

# Load environment variables from the RAG_project .env file if available.
# This is required when the backend runs from the `backend/` folder and the
# current working directory is not the RAG_project root.
env_path = PACKAGE_ROOT / '.env'
if env_path.exists():
    load_dotenv(env_path)
else:
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
    Calls Groq's OpenAI-compatible API (https://api.groq.com/openai/v1)
    using the plain `openai` SDK, just with a swapped base_url — this is
    GroqCloud (fast LPU inference), not xAI's Grok.
    """

    def __init__(self):

        api_key = os.getenv("GROQ_API_KEY")

        if api_key is None:
            raise ValueError("GROQ_API_KEY not found.")

        logger.info(f"Loading {LLM_MODEL}")

        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1"
        )

        logger.info("Groq Loaded")

    def generate(self, prompt: str) -> str:

        response = self.client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=TEMPERATURE,
            max_tokens=MAX_OUTPUT_TOKENS,
            top_p=TOP_P
        )

        return response.choices[0].message.content.strip()