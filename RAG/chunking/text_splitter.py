from typing import List
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from langchain_text_splitters import RecursiveCharacterTextSplitter

from loaders.pdf_loader import Document
from config import CHUNK_SIZE, CHUNK_OVERLAP


class TextSplitter:
    """
    Splits full-page Documents (one per PDF page) into smaller Documents
    ("chunks") sized for the embedding model + retriever.

    Why RecursiveCharacterTextSplitter specifically:
    Unlike a fixed-size splitter (which just cuts every N characters, even
    mid-sentence), this one tries each separator in order and only falls
    back to the next one if the chunk is still too big. So it prefers to
    break on paragraph boundaries first, then lines, then sentences, then
    words — only cutting mid-word as an absolute last resort. This keeps
    chunks semantically coherent, which matters a lot for embedding quality.
    """

    def __init__(self):
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,       # max characters per chunk (from config.py = 1000)
            chunk_overlap=CHUNK_OVERLAP, # characters repeated between consecutive chunks (200)
            # Overlap exists so a sentence that gets cut at a chunk boundary
            # still has its surrounding context in the *next* chunk too —
            # otherwise the retriever could return a chunk that starts
            # mid-thought with no way to recover what came before it.

            separators=[
                "\n\n",  # 1st choice: paragraph breaks — cleanest possible split
                "\n",    # 2nd: line breaks (also where our table rows land,
                         #      since pdf_loader joins table rows with "\n")
                ". ",    # 3rd: sentence boundaries
                " ",     # 4th: word boundaries — last resort before...
                ""       # 5th: hard character cut — only if a single "word"
                         #      (e.g. a long formula or URL) exceeds chunk_size
            ],
            # Order matters: the splitter tries separators[0] first on the
            # whole text, and only recurses into separators[1] for pieces
            # that are still bigger than chunk_size, and so on.
        )

    def split_documents(self, documents: List[Document]) -> List[Document]:
        """
        Takes page-level Documents (from PDFLoader) and returns
        chunk-level Documents ready for embedding.
        """
        all_chunks = []

        for document in documents:

            # Nothing to split if the page had no usable text
            # (shouldn't happen since PDFLoader already drops empty pages,
            # but guards against a degenerate 1-2 char page slipping through)
            if not document.page_content.strip():
                continue

            # split_text returns a plain list[str] — no metadata yet,
            # that's why we have to rebuild Document objects below
            chunks = self.splitter.split_text(document.page_content)

            for chunk_index, chunk in enumerate(chunks):

                # .copy() is important here — without it every chunk from
                # this page would share the *same* metadata dict by
                # reference, so setting "chunk" on one would silently
                # overwrite it for all of them
                metadata = document.metadata.copy()

                metadata["chunk"] = chunk_index + 1
                metadata["total_chunks_in_page"] = len(chunks)

                # A stable unique ID per chunk — useful later for
                # upserting into FAISS/vectorstore without duplicates,
                # and for tracing a retrieved chunk back to its exact
                # source + page + position
                metadata["chunk_id"] = (
                    f"{document.metadata.get('source', 'unknown')}"
                    f"_p{document.metadata.get('page', 0)}"
                    f"_c{chunk_index + 1}"
                )

                all_chunks.append(
                    Document(
                        page_content=chunk,
                        metadata=metadata
                    )
                )

        return all_chunks