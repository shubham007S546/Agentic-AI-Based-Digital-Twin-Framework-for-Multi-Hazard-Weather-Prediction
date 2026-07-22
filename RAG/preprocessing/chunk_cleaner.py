"""
Chunk Cleaner
-------------
Cleans page-level or chunk-level Documents before/after splitting.

Two separate concerns, kept as two separate passes because they operate
at different granularities:

  1. TEXT/BOILERPLATE CLEANING (clean_documents)
     Runs per-document. Strips URLs, publisher boilerplate (Elsevier/
     IEEE/Springer lines, DOIs, copyright notices), page numbers, and
     — importantly — repeated running headers/footers that are IDENTICAL
     across most pages of the same PDF (journal name repeated on every
     page, "IEEE Transactions on X, Vol. Y" etc). Static regexes can't
     catch every journal's exact header text, so instead we detect
     "this exact line shows up on 60%+ of this PDF's pages" and strip it
     — that generalizes to any publisher without hardcoding their format.

  2. QUALITY FILTERING + TINY-CHUNK MERGING (filter_and_merge)
     Runs after chunking. Drops chunks that are pure noise (OCR garbage,
     stray table fragments, mostly symbols/numbers) and merges chunks
     that are too small to carry meaningful context into their neighbor
     — instead of just dropping them, which would silently lose content.

Section titles (Abstract, Introduction, Results, Conclusion, etc.) are
never touched by any pattern here — none of the boilerplate regexes can
match a bare section heading, so they pass through untouched by design.
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import re
from collections import Counter, defaultdict
from typing import List

from loaders.pdf_loader import Document
from utils.logger import logger


# -------------------------------
# Tunable knobs
# -------------------------------
MIN_DOCUMENT_LENGTH = 100        # drop a whole page/doc if less text than this survives cleaning
MIN_CHUNK_LENGTH = 150           # chunks shorter than this get merged into a neighbor, not dropped
MIN_ALPHA_RATIO = 0.4            # if <40% of chars are letters, it's probably garbled/table noise
HEADER_FOOTER_MIN_PAGES = 3      # need at least this many pages from a source before we trust the pattern
HEADER_FOOTER_FREQUENCY = 0.6    # a line appearing on 60%+ of a source's pages = running header/footer
HEADER_FOOTER_MAX_LINE_LEN = 120 # headers/footers are short; don't nuke a long repeated sentence by mistake

# Front-matter (journal name / paper title / author list / affiliations)
# only appears ONCE, on page 1 — so the repeated-header detector above
# can never catch it (it only flags lines that repeat across many pages).
# "Abstract" is the one heading that's near-universal across ScienceDirect,
# IEEE, and Springer papers and always comes right after this front matter,
# so cutting everything before it is far more reliable than trying to
# pattern-match every possible journal-name/author-list format.
#
# Two variants because PDF extraction is inconsistent about how a heading
# comes out: normally it's just the word "abstract" on its own line, but
# two-column layouts with letter-spaced/tracked headings often extract as
# "A B S T R A C T" (each letter separated by a space) instead.
FRONT_MATTER_STOP_PATTERN = re.compile(r"\babstract\b", re.IGNORECASE)
FRONT_MATTER_STOP_PATTERN_SPACED = re.compile(r"\ba\s*b\s*s\s*t\s*r\s*a\s*c\s*t\b", re.IGNORECASE)

# Fallback heuristics for when "Abstract" isn't found on page 1 (rare
# layouts, or OCR mangled the word) — catches the most common front-matter
# line shapes without touching real body text elsewhere.
AFFILIATION_LINE_PATTERN = re.compile(
    r"^.{0,15}\b(University|Institute|Department|College|Laborator(y|ies)|"
    r"School of|Faculty of)\b.*$",
    re.IGNORECASE | re.MULTILINE,
)
EMAIL_LINE_PATTERN = re.compile(r"^.*\S+@\S+\.\S+.*$", re.MULTILINE)
# Author-list lines: several "Firstname Lastname" tokens joined by commas,
# optionally with a superscript-style marker (a, b, *, 1, 2) stuck on —
# e.g. "Sandipp Krishna Ravi a, Yigitcan Comlek b, Arjun Kumar"
AUTHOR_LIST_LINE_PATTERN = re.compile(
    r"^(?:[A-Z][a-zA-Z.\-]+\s+){1,4}[A-Z][a-zA-Z.\-]+\s*[a-z\*,\d]{0,3}"
    r"(?:\s*,\s*(?:[A-Z][a-zA-Z.\-]+\s+){1,4}[A-Z][a-zA-Z.\-]+\s*[a-z\*,\d]{0,3}){1,}\s*$",
    re.MULTILINE,
)


class ChunkCleaner:

    # ===========================================================
    # PASS 1 — per-document text cleaning
    # ===========================================================

    def remove_urls(self, text: str) -> str:
        """Strips raw URLs and DOI links (ScienceDirect/Elsevier pages are
        full of both — journal homepage links, doi.org links, etc.)"""
        text = re.sub(r"https?://\S+", "", text)
        text = re.sub(r"www\.\S+", "", text)
        text = re.sub(r"\bdoi:\s*\S+", "", text, flags=re.IGNORECASE)
        return text

    def remove_boilerplate(self, text: str) -> str:
        """Publisher/journal boilerplate lines common across ScienceDirect,
        IEEE, Springer, and Elsevier papers. Each pattern targets a full
        line (anchored with re.MULTILINE + ^...$) so it can't accidentally
        eat into real body text that merely contains one of these words."""
        patterns = [
            r"^Contents lists available at ScienceDirect.*$",
            r"^journal homepage:?.*$",
            r"^.*Elsevier (Ltd|B\.?V\.?|Inc\.?).*(All rights reserved)?.*$",
            r"^©.*\d{4}.*(Elsevier|IEEE|Springer|Publishing).*$",
            r"^This is an open access article under the CC.*license.*$",
            r"^\s*Research paper\s*$",
            r"^\s*Review [Aa]rticle\s*$",
            r"^\s*Original [Aa]rticle\s*$",
            r"^Received\s*:?\s*\d.*$",
            r"^Accepted\s*:?\s*\d.*$",
            r"^Published\s*:?\s*\d.*$",
            r"^Available online.*$",
            r"^ISSN\s*:?\s*[\d\-Xx]+.*$",
            r"^Vol\.?\s*\d+.*No\.?\s*\d+.*$",           # "Vol. 12, No. 3, pp. 45-60"
            r"^IEEE Transactions on .*$",
            r"^Springer Nature.*$",
            r"^\s*Corresponding author.*$",
        ]
        for pattern in patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE | re.MULTILINE)
        return text

    def remove_page_numbers(self, text: str) -> str:
        """Two forms show up: explicit 'Page 5' text, and — far more common
        after PDF extraction — a lone number sitting alone on its own line
        where the page footer used to be."""
        text = re.sub(r"\bPage\s+\d+\b", "", text, flags=re.IGNORECASE)
        # A line containing ONLY a number (and optional punctuation) — e.g. "7" or "- 7 -"
        text = re.sub(r"^\s*[-–—]?\s*\d{1,4}\s*[-–—]?\s*$", "", text, flags=re.MULTILINE)
        return text

    def normalize_spaces(self, text: str) -> str:
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def remove_empty_lines(self, text: str) -> str:
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        return "\n".join(lines)

    def remove_front_matter(self, text: str) -> str:
        """
        PDF-ONLY. Only call this on page-1 text of an actual research
        paper. Strips the journal name, paper title repeat, author list,
        and affiliation block that sit above the Abstract — none of that
        is retrievable/useful content and it pollutes the very first
        chunk of every paper.

        Primary strategy: find "Abstract" anywhere in the page (not
        anchored to line-start — extraction doesn't reliably put it on
        its own clean line) and cut everything before it. The heading
        itself is KEPT — section titles are never dropped. Tries a
        letter-spaced variant too ("A B S T R A C T"), since tracked/
        bold headings sometimes extract with gaps between each letter.

        Fallback (only if neither pattern matches anywhere on the page):
        strip lines that look like affiliations/emails/author lists
        individually — there's no reliable cut point in that case.
        """
        match = FRONT_MATTER_STOP_PATTERN.search(text) or FRONT_MATTER_STOP_PATTERN_SPACED.search(text)
        if match:
            return text[match.start():]

        # Fallback — "Abstract" doesn't appear anywhere on this page at
        # all, which usually means the PDF's layout scrambled it out of
        # the extracted reading order. Worth knowing about, so log it.
        logger.warning(
            "Front-matter cleanup: no 'Abstract' heading found on this PDF page "
            "— falling back to line-level affiliation/author stripping, "
            "which is less reliable. Check extraction if this page's "
            "output still looks messy."
        )
        text = AFFILIATION_LINE_PATTERN.sub("", text)
        text = EMAIL_LINE_PATTERN.sub("", text)
        text = AUTHOR_LIST_LINE_PATTERN.sub("", text)
        return text

    def clean_text(self, text: str) -> str:
        """Single-document cleaning, no cross-page knowledge needed."""
        text = self.remove_urls(text)
        text = self.remove_boilerplate(text)
        text = self.remove_page_numbers(text)
        text = self.normalize_spaces(text)
        text = self.remove_empty_lines(text)
        return text

    # ===========================================================
    # Repeated header/footer detection — needs ALL pages of a source
    # at once, which is why this is separate from clean_text above.
    # ===========================================================

    def _find_repeated_lines(self, documents: List[Document]) -> dict:
        """
        For each source PDF, count how many of its pages contain each
        exact line. A line that recurs on most pages (same journal name,
        same running title, same "© Elsevier" footer) is almost certainly
        a header/footer artifact rather than real content — real body
        text essentially never repeats verbatim across many different
        pages.

        Returns: {source_filename: set(lines_to_strip)}
        """
        lines_by_source = defaultdict(list)  # source -> list of (page, set(lines on that page))

        for doc in documents:
            source = doc.metadata.get("source", "unknown")
            page_lines = {line.strip() for line in doc.page_content.split("\n") if line.strip()}
            lines_by_source[source].append(page_lines)

        repeated_by_source = {}

        for source, pages in lines_by_source.items():
            if len(pages) < HEADER_FOOTER_MIN_PAGES:
                # Not enough pages to trust a frequency pattern — skip,
                # otherwise a 2-page PDF would have every line "repeated"
                repeated_by_source[source] = set()
                continue

            line_counter = Counter()
            for page_lines in pages:
                line_counter.update(page_lines)

            threshold = max(2, int(len(pages) * HEADER_FOOTER_FREQUENCY))

            repeated = {
                line for line, count in line_counter.items()
                if count >= threshold and len(line) <= HEADER_FOOTER_MAX_LINE_LEN
            }
            repeated_by_source[source] = repeated

        return repeated_by_source

    def strip_repeated_headers_footers(self, documents: List[Document]) -> List[Document]:
        """Removes lines that repeat across most pages of the same source."""
        repeated_by_source = self._find_repeated_lines(documents)

        cleaned = []
        for doc in documents:
            source = doc.metadata.get("source", "unknown")
            repeated = repeated_by_source.get(source, set())

            if not repeated:
                cleaned.append(doc)
                continue

            kept_lines = [
                line for line in doc.page_content.split("\n")
                if line.strip() not in repeated
            ]
            new_text = self.normalize_spaces("\n".join(kept_lines))

            cleaned.append(Document(page_content=new_text, metadata=doc.metadata))

        return cleaned

    # ===========================================================
    # Full document-level cleaning pipeline
    # ===========================================================

    def clean_documents(self, documents: List[Document]) -> List[Document]:
        """
        Run this BEFORE chunking (on page-level Documents from PDFLoader
        and/or WebLoader). Order matters: front-matter stripping first
        (only affects page 1 of PDFs, and has to run before boilerplate
        regexes chew up the "Abstract" marker it depends on), then
        per-line boilerplate regexes, then cross-page repeated-header
        detection (needs the noise gone first so it isn't comparing
        against junk), then drop near-empty pages.
        """
        # Step 1: strip title/authors/affiliations — PDF page 1 ONLY.
        # WebLoader also numbers its first section "page: 1", but it's
        # not a research paper and has no such front matter to strip, so
        # gate this on source_type == "pdf" (defaults to "pdf" for any
        # older Document that predates this field, preserving old
        # behavior for existing pipelines).
        stage0 = []
        for doc in documents:
            is_pdf = doc.metadata.get("source_type", "pdf") == "pdf"
            if is_pdf and doc.metadata.get("page") == 1:
                text = self.remove_front_matter(doc.page_content)
            else:
                text = doc.page_content
            stage0.append(Document(page_content=text, metadata=doc.metadata))

        # Step 2: per-document regex cleaning
        stage1 = []
        for doc in stage0:
            text = self.clean_text(doc.page_content)
            stage1.append(Document(page_content=text, metadata=doc.metadata))

        # Step 3: cross-page repeated header/footer stripping (needs all
        # pages of the same source together, hence a separate full pass)
        stage2 = self.strip_repeated_headers_footers(stage1)

        # Step 4: drop pages that have basically nothing left
        cleaned = []
        for doc in stage2:
            if len(doc.page_content) >= MIN_DOCUMENT_LENGTH:
                cleaned.append(doc)
            else:
                source = doc.metadata.get("source", "unknown")
                page = doc.metadata.get("page", "?")
                logger.warning(
                    f"Dropping {source} page {page}: only {len(doc.page_content)} chars "
                    f"survived cleaning (need >= {MIN_DOCUMENT_LENGTH}). Likely a "
                    f"navigation/widget-heavy page with little real prose content "
                    f"(common on homepages) rather than an article."
                )

        return cleaned

    # ===========================================================
    # PASS 2 — chunk-level quality filtering + tiny-chunk merging
    # Run this AFTER TextSplitter.split_documents()
    # ===========================================================

    def _alpha_ratio(self, text: str) -> float:
        if not text:
            return 0.0
        letters = sum(1 for ch in text if ch.isalpha())
        return letters / len(text)

    def _is_low_quality(self, text: str) -> bool:
        """Catches OCR garbage, stray table fragments, reference-list
        numbering runs, and other non-prose noise that survived chunking."""
        stripped = text.strip()
        if len(stripped) < 20:
            return True
        if self._alpha_ratio(stripped) < MIN_ALPHA_RATIO:
            return True
        # A chunk that's just repeated punctuation/whitespace artifacts
        if re.fullmatch(r"[\W\d_]+", stripped):
            return True
        return False

    def filter_and_merge(self, chunks: List[Document]) -> List[Document]:
        """
        1. Drop chunks that are pure noise (_is_low_quality).
        2. Merge chunks smaller than MIN_CHUNK_LENGTH into the next chunk
           FROM THE SAME PAGE — merging across different pages/sources
           would splice unrelated content together, so we never do that;
           a tiny chunk at the very end of a page/source with no valid
           neighbor to merge into is kept as-is rather than dropped.
        """
        # Step 1: drop garbage chunks outright
        chunks = [c for c in chunks if not self._is_low_quality(c.page_content)]

        merged = []
        buffer_doc = None

        for chunk in chunks:
            if buffer_doc is None:
                buffer_doc = chunk
                continue

            same_page = (
                buffer_doc.metadata.get("source") == chunk.metadata.get("source")
                and buffer_doc.metadata.get("page") == chunk.metadata.get("page")
            )

            if len(buffer_doc.page_content) < MIN_CHUNK_LENGTH and same_page:
                # fold buffer into the current chunk rather than emitting
                # a too-small chunk on its own
                merged_text = f"{buffer_doc.page_content}\n{chunk.page_content}"
                merged_metadata = chunk.metadata.copy()
                merged_metadata["merged_from_chunks"] = [
                    buffer_doc.metadata.get("chunk"), chunk.metadata.get("chunk")
                ]
                buffer_doc = Document(page_content=merged_text, metadata=merged_metadata)
            else:
                merged.append(buffer_doc)
                buffer_doc = chunk

        if buffer_doc is not None:
            merged.append(buffer_doc)

        return merged