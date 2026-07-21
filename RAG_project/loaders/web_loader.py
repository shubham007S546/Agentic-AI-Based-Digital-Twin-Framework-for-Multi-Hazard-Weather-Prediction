"""
Robust Website Loader
----------------------
Fetches web pages and converts them into the SAME Document schema used
by PDFLoader (page_content + metadata: source, page, ...), so
build_index.py can mix PDFs and websites into one unified corpus with
zero changes to chunking, embedding, retrieval, or prompt building —
they all just see Document objects either way.

Pipeline per URL:
  1. Fetch with retries + timeout + a real User-Agent (many sites block
     the default python-requests UA)
  2. Extract clean, boilerplate-free article text via trafilatura
     (falls back to BeautifulSoup text extraction if trafilatura fails
     or isn't installed)
  3. Split into per-section "pages" (~1500 chars each) so long articles
     get citeable Page numbers just like a PDF, instead of one giant blob
  4. Clean + package into Document objects with rich metadata
  5. Never let one bad URL kill the whole run
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import re
import time
import requests
from urllib.parse import urlparse

from loaders.pdf_loader import Document
from utils.logger import logger
from utils.text_cleaner import clean_text

try:
    import trafilatura
    TRAFILATURA_AVAILABLE = True
except ImportError:
    TRAFILATURA_AVAILABLE = False

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

from bs4 import BeautifulSoup


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.google.com/",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}
REQUEST_TIMEOUT = 15
MAX_RETRIES = 2
RETRY_BACKOFF_SECONDS = 2
SECTION_TARGET_LENGTH = 1500
MIN_SECTION_LENGTH = 200  # merge a too-small trailing section into the previous one
PLAYWRIGHT_TIMEOUT_MS = 20000
PLAYWRIGHT_RENDER_WAIT_MS = 1500  # let JS finish rendering after page load

# Some CDNs/WAFs (Akamai, Cloudflare, Incapsula...) return HTTP 200 with a
# denial page instead of a clean 403 — e.g. "Access Denied ... Reference
# #18.xxxxx". These look like valid, non-empty HTML to every check above,
# so they'd otherwise get indexed as if they were the real article. Catch
# the common signatures and treat them as a failed fetch instead.
_BLOCK_PAGE_SIGNATURES = [
    "access denied",
    "reference #",
    "you don't have permission to access",
    "request unsuccessful",
    "attention required! | cloudflare",
    "sorry, you have been blocked",
    "please enable cookies",
    "checking your browser before accessing",
    "incapsula incident id",
]
_BLOCK_PAGE_MIN_MATCH_LENGTH = 400  # below this, short "Access denied" mentions inside real articles won't false-positive


def _looks_like_block_page(text: str) -> bool:
    if not text or len(text) > _BLOCK_PAGE_MIN_MATCH_LENGTH:
        # Long real articles occasionally mention "access denied" in
        # passing (e.g. discussing a security incident) — only apply
        # this check to short pages, where a WAF block page is by far
        # the more likely explanation.
        return False
    lowered = text.lower()
    return any(sig in lowered for sig in _BLOCK_PAGE_SIGNATURES)


class WebLoader:

    def __init__(self, urls=None, url_file: Path = None, use_playwright_fallback: bool = True):
        """
        urls: explicit list of URLs to load
        url_file: path to a text file with one URL per line (blank
                  lines and lines starting with # are ignored)
        use_playwright_fallback: if a plain requests.get() fails (403,
                  empty content, JS-only page), retry with a headless
                  browser that actually renders the page. Requires:
                      pip install playwright
                      playwright install chromium
                  Silently skipped (with a log line) if not installed.
        """
        self.urls = list(urls) if urls else []
        self.use_playwright_fallback = use_playwright_fallback and PLAYWRIGHT_AVAILABLE

        if use_playwright_fallback and not PLAYWRIGHT_AVAILABLE:
            logger.warning(
                "use_playwright_fallback=True but playwright isn't installed — "
                "falling back to plain requests only. Install with: "
                "pip install playwright && playwright install chromium"
            )

        if url_file is not None:
            url_file = Path(url_file)
            if url_file.exists():
                with open(url_file, "r", encoding="utf-8") as f:
                    file_urls = [
                        line.strip() for line in f
                        if line.strip() and not line.strip().startswith("#")
                    ]
                self.urls.extend(file_urls)
            else:
                logger.info(f"No URL file at {url_file} — skipping (this is fine if you have none)")

        # De-dupe, preserve order
        seen = set()
        deduped = []
        for u in self.urls:
            if u not in seen:
                seen.add(u)
                deduped.append(u)
        self.urls = deduped

    # ---------------------------------------------------------
    # Step 1: Fetch with retries
    # ---------------------------------------------------------
    def _fetch(self, url: str) -> str:
        headers = DEFAULT_HEADERS

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
                response.raise_for_status()
                return response.text
            except requests.RequestException as e:
                logger.warning(f"[{attempt}/{MAX_RETRIES}] Failed to fetch {url}: {e}")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_BACKOFF_SECONDS * attempt)

        logger.error(f"Giving up on {url} after {MAX_RETRIES} attempts")
        return ""

    # ---------------------------------------------------------
    # Step 1b: Headless-browser fallback for JS-rendered / bot-protected
    # pages that reject plain requests.get() (403, empty body, etc.)
    # ---------------------------------------------------------
    def _fetch_with_playwright(self, url: str) -> str:
        if not self.use_playwright_fallback:
            return ""

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=USER_AGENT,
                    locale="en-US",
                )
                page = context.new_page()
                page.goto(url, timeout=PLAYWRIGHT_TIMEOUT_MS, wait_until="domcontentloaded")
                # Give client-side JS a moment to finish rendering content
                page.wait_for_timeout(PLAYWRIGHT_RENDER_WAIT_MS)
                html = page.content()
                browser.close()
                return html
        except Exception as e:
            logger.warning(f"Playwright fetch failed for {url}: {e}")
            return ""

    # ---------------------------------------------------------
    # Step 2: Extract clean article text (+ title)
    # ---------------------------------------------------------
    def _extract(self, html: str, url: str):
        title = None

        if TRAFILATURA_AVAILABLE:
            try:
                extracted = trafilatura.extract(
                    html,
                    include_tables=True,
                    include_formatting=False,
                    with_metadata=True,
                    output_format="txt",
                )
                meta = trafilatura.extract_metadata(html)
                title = meta.title if meta and meta.title else None
                if extracted and extracted.strip():
                    return extracted, title
            except Exception as e:
                logger.warning(f"trafilatura extraction failed for {url}, falling back to BeautifulSoup: {e}")

        # Fallback: plain BeautifulSoup text extraction
        try:
            soup = BeautifulSoup(html, "html.parser")

            if soup.title and soup.title.string:
                title = soup.title.string.strip()

            for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
                tag.decompose()

            text = soup.get_text(separator="\n")
            text = re.sub(r"\n{3,}", "\n\n", text)
            return text.strip(), title
        except Exception as e:
            logger.error(f"BeautifulSoup extraction failed for {url}: {e}")
            return "", title

    # ---------------------------------------------------------
    # Step 3: Split into section "pages" so long articles get
    # citeable page numbers, same UX as PDF pages
    # ---------------------------------------------------------
    def _split_into_sections(self, text: str) -> list:
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

        sections = []
        current = []
        current_len = 0

        for para in paragraphs:
            current.append(para)
            current_len += len(para)
            if current_len >= SECTION_TARGET_LENGTH:
                sections.append("\n\n".join(current))
                current = []
                current_len = 0

        if current:
            if sections and current_len < MIN_SECTION_LENGTH:
                sections[-1] += "\n\n" + "\n\n".join(current)
            else:
                sections.append("\n\n".join(current))

        return sections if sections else [text]

    # ---------------------------------------------------------
    # Step 4: Load one URL end-to-end
    # ---------------------------------------------------------
    def load_url(self, url: str) -> list:
        documents = []
        fetch_method = "requests"

        html = self._fetch(url)

        if not html and self.use_playwright_fallback:
            logger.info(f"Plain fetch failed for {url}, retrying with headless browser...")
            html = self._fetch_with_playwright(url)
            fetch_method = "playwright"

        if not html:
            return documents

        text, title = self._extract(html, url)
        if not text or not text.strip():
            logger.warning(f"No extractable text from {url} (fetched via {fetch_method})")
            return documents

        if _looks_like_block_page(text) or (title and _looks_like_block_page(title)):
            logger.error(
                f"{url} returned what looks like a CDN/WAF block page "
                f"(e.g. 'Access Denied', 'Reference #...') rather than real "
                f"content, even though the HTTP request itself succeeded. "
                f"Skipping — this site is actively blocking automated access "
                f"to this URL. Fetched via: {fetch_method}."
            )
            return documents

        domain = urlparse(url).netloc
        display_source = title if title else domain

        sections = self._split_into_sections(text)

        for idx, section_text in enumerate(sections, start=1):
            section_text = clean_text(section_text)
            if not section_text.strip():
                continue

            metadata = {
                "source": display_source,
                "page": idx,               # "page" = section number, so citations
                "total_pages": len(sections),  # look identical to PDF citations downstream
                "url": url,
                "source_type": "web",      # lets ChunkCleaner skip PDF-only front-matter stripping
                "extraction_method": "trafilatura" if TRAFILATURA_AVAILABLE else "beautifulsoup",
                "fetch_method": fetch_method,
                "has_tables": False,
                "has_equations": False,
                "has_images": False,
                "image_count": 0,
                "image_paths": [],
            }

            documents.append(Document(page_content=section_text, metadata=metadata))

        logger.info(f"Loaded {len(documents)} section(s) from {url} (via {fetch_method})")
        return documents

    # ---------------------------------------------------------
    # Step 5: Load every URL, never let one bad site kill the batch
    # ---------------------------------------------------------
    def load_all_urls(self) -> list:
        all_documents = []

        if not self.urls:
            logger.info("No URLs configured — WebLoader has nothing to load")
            return all_documents

        logger.info(f"Loading {len(self.urls)} URL(s)")

        for url in self.urls:
            try:
                docs = self.load_url(url)
                all_documents.extend(docs)
            except Exception as e:
                logger.error(f"Unhandled error loading {url}: {e}")
                continue

        logger.info(f"Total Documents Loaded from web: {len(all_documents)}")
        return all_documents


if __name__ == "__main__":
    loader = WebLoader(urls=["https://arxiv.org/abs/2210.03629"])
    docs = loader.load_all_urls()
    print(f"Loaded {len(docs)} documents total")
    for d in docs[:3]:
        print(d.metadata)
        print(d.page_content[:200])
        print("---")