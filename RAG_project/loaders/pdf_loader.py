"""
Robust Multi-PDF Loader
------------------------
Pipeline per PDF:
  1. Discover all PDFs in data dir
  2. Safely open (handles corruption + password-protected files)
  3. Per page: extract native text, unicode-safe (preserves math symbols,
     accents, special chars — no lossy compatibility folding)
  4. If native text too short -> OCR fallback (scanned/image pages)
  5. Detect equation-heavy text (Greek letters, math operators, math
     unicode alphanumerics) and flag it — optional LaTeX-OCR for pages
     that are actually formula images (opt-in, heavy dependency)
  6. Extract tables (pdfplumber) and append as pipe-delimited text
  7. Extract embedded images/figures to disk, reference path in metadata
     (for later captioning by a vision LLM, not done here — keep it simple)
  8. Clean + package into Document objects with rich metadata
  9. Aggregate across all PDFs, never let one bad file kill the run
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))
import unicodedata
from pathlib import Path
from dataclasses import dataclass, field

import fitz  # PyMuPDF
import pdfplumber
from PIL import Image
from tqdm import tqdm

try:
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

from config import DATA_DIR, BASE_DIR
from utils.logger import logger
from RAG_project.utils.text_cleaner import clean_text


# -------------------------------
# Tunable knobs
# -------------------------------
MIN_TEXT_LENGTH_FOR_NATIVE = 20   # below this char count -> treat page as scanned
OCR_DPI = 300
OCR_LANGUAGES = "eng"
MAX_IMAGES_LOGGED_PER_PAGE = 5

# Use NFC, not NFKC. NFKC does *compatibility* folding — it will quietly
# turn math/formatting unicode like a mathematical script X or the
# blackboard-bold R symbol into plain ASCII letters, which destroys the
# meaning of equations. NFC just normalizes accent composition and is
# safe for special characters and math symbols.
NORMALIZE_FORM = "NFC"

EXTRACTED_IMAGES_DIR = BASE_DIR / "data" / "extracted_images"

# Unicode ranges that signal "this text contains math", used for a cheap
# heuristic flag — no heavy NLP/model needed for the common case.
_MATH_RANGES = [
    (0x0370, 0x03FF),    # Greek letters (alpha, beta, theta, Sigma, Delta ...)
    (0x2200, 0x22FF),    # Math operators (sum, integral, sqrt, +-, <=, >=, infinity ...)
    (0x2100, 0x214F),    # Letterlike symbols (R, Z, N blackboard-bold ...)
    (0x2150, 0x218F),    # Number forms (fractions, roman numerals)
    (0x1D400, 0x1D7FF),  # Mathematical alphanumeric symbols
    (0x2070, 0x209F),    # Super/subscripts
]
_MATH_DENSITY_THRESHOLD = 0.01  # >1% of chars being math symbols -> flag it


@dataclass
class Document:
    """Represents one page (or table/figure-augmented page) of a PDF,
    OR one section of a web page (see loaders/web_loader.py) — both
    loaders emit this same shape so downstream code (cleaning, chunking,
    embedding, retrieval, prompt building) never needs to know which
    source type a Document came from."""
    page_content: str
    metadata: dict = field(default_factory=dict)


class PDFLoader:

    def __init__(
        self,
        data_directory: Path,
        enable_ocr: bool = True,
        enable_tables: bool = True,
        enable_figure_extraction: bool = True,
        enable_equation_ocr: bool = False,  # opt-in, needs pix2tex + torch
    ):
        self.data_directory = Path(data_directory)
        self.enable_tables = enable_tables
        self.enable_ocr = enable_ocr and OCR_AVAILABLE
        self.enable_figure_extraction = enable_figure_extraction
        self.enable_equation_ocr = enable_equation_ocr
        self._latex_ocr_model = None  # lazy-loaded, only if actually used

        if enable_ocr and not OCR_AVAILABLE:
            logger.warning(
                "pytesseract not installed — OCR fallback disabled. "
                "Install with: pip install pytesseract Pillow, "
                "and install the tesseract-ocr system binary."
            )

    # ---------------------------------------------------------
    # Step 1: Discover PDFs
    # ---------------------------------------------------------
    def get_pdf_files(self):
        pdf_files = sorted(self.data_directory.glob("*.pdf"))
        logger.info(f"Found {len(pdf_files)} PDF files in {self.data_directory}")
        if not pdf_files:
            logger.warning(f"No PDFs found in {self.data_directory}")
        return pdf_files

    # ---------------------------------------------------------
    # Step 2: Open safely — handles corruption + encryption
    # ---------------------------------------------------------
    def _open_pdf(self, pdf_path: Path):
        try:
            pdf = fitz.open(pdf_path)
        except Exception as e:
            logger.error(f"Cannot open {pdf_path.name}: {e}")
            return None

        if pdf.is_encrypted:
            if pdf.authenticate("") == 0:
                logger.error(
                    f"{pdf_path.name} is password protected — "
                    "empty-password auth failed. Skipping."
                )
                pdf.close()
                return None
            logger.warning(f"{pdf_path.name} was encrypted; authenticated with empty password")

        if pdf.page_count == 0:
            logger.error(f"{pdf_path.name} has 0 pages — likely corrupted")
            pdf.close()
            return None

        return pdf

    # ---------------------------------------------------------
    # Step 3: Native text extraction — encoding/special-char safe
    # ---------------------------------------------------------
    def _extract_native_text(self, page) -> str:
        try:
            text = page.get_text("text")
        except Exception as e:
            logger.warning(f"Native text extraction failed on page {page.number + 1}: {e}")
            return ""

        if not text:
            return ""

        text = unicodedata.normalize(NORMALIZE_FORM, text)
        # Strip stray control chars some PDF encoders inject, but keep
        # every printable char (math symbols, accented letters, etc.)
        text = "".join(ch for ch in text if ch in ("\n", "\t") or ch.isprintable())
        return text

    # ---------------------------------------------------------
    # Step 4: Cheap heuristic — does this text look equation-heavy?
    # ---------------------------------------------------------
    def _math_density(self, text: str) -> float:
        if not text:
            return 0.0
        math_chars = sum(
            1 for ch in text
            if any(lo <= ord(ch) <= hi for lo, hi in _MATH_RANGES)
        )
        return math_chars / max(len(text), 1)

    def _has_equations(self, text: str) -> bool:
        return self._math_density(text) >= _MATH_DENSITY_THRESHOLD

    # ---------------------------------------------------------
    # Step 5: OCR fallback for scanned / image-only pages
    # ---------------------------------------------------------
    def _page_to_image(self, page, dpi: int = OCR_DPI) -> Image.Image:
        zoom = dpi / 72
        matrix = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=matrix, colorspace=fitz.csRGB)
        return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    def _ocr_page(self, page) -> str:
        if not self.enable_ocr:
            return ""
        try:
            img = self._page_to_image(page)
            return pytesseract.image_to_string(img, lang=OCR_LANGUAGES).strip()
        except Exception as e:
            logger.warning(f"OCR failed on page {page.number + 1}: {e}")
            return ""

    def _load_latex_ocr(self):
        """Lazy-load pix2tex only if a caller actually needs equation OCR.
        Keeps the loader lightweight for the common (non-formula-scan) case."""
        if self._latex_ocr_model is not None:
            return self._latex_ocr_model
        try:
            from pix2tex.cli import LatexOCR
            self._latex_ocr_model = LatexOCR()
            logger.info("LaTeX-OCR (pix2tex) model loaded for equation recognition")
        except ImportError:
            logger.warning(
                "enable_equation_ocr=True but pix2tex not installed. "
                "Install with: pip install pix2tex torch. Falling back to plain OCR."
            )
            self._latex_ocr_model = False
        return self._latex_ocr_model

    def _ocr_equation_page(self, page) -> str:
        """Only called for pages already flagged as scanned; only used when
        enable_equation_ocr=True. Returns LaTeX text for formula pages."""
        model = self._load_latex_ocr()
        if not model:
            return self._ocr_page(page)
        try:
            img = self._page_to_image(page)
            return model(img)  # returns LaTeX string
        except Exception as e:
            logger.warning(f"LaTeX-OCR failed on page {page.number + 1}, falling back to plain OCR: {e}")
            return self._ocr_page(page)

    # ---------------------------------------------------------
    # Step 6: Table extraction via pdfplumber (page-index aligned with fitz)
    # ---------------------------------------------------------
    def _extract_tables_for_page(self, plumber_pdf, page_number: int) -> str:
        if not self.enable_tables or plumber_pdf is None:
            return ""

        try:
            plumber_page = plumber_pdf.pages[page_number]
            tables = plumber_page.extract_tables()
        except Exception as e:
            logger.warning(f"Table extraction failed on page {page_number + 1}: {e}")
            return ""

        if not tables:
            return ""

        rendered = []
        for t_idx, table in enumerate(tables):
            rendered.append(f"\n[Table {t_idx + 1}]")
            for row in table:
                clean_row = [str(cell).strip() if cell is not None else "" for cell in row]
                rendered.append(" | ".join(clean_row))

        return "\n".join(rendered)

    # ---------------------------------------------------------
    # Step 7: Extract embedded images/figures to disk
    # ---------------------------------------------------------
    def _extract_figures(self, pdf, page, pdf_path: Path, page_number: int) -> list:
        if not self.enable_figure_extraction:
            return []

        try:
            image_list = page.get_images(full=True)
        except Exception:
            return []

        if not image_list:
            return []

        out_dir = EXTRACTED_IMAGES_DIR / pdf_path.stem
        out_dir.mkdir(parents=True, exist_ok=True)

        saved = []
        for img_idx, img in enumerate(image_list[:MAX_IMAGES_LOGGED_PER_PAGE]):
            xref = img[0]
            try:
                base_image = pdf.extract_image(xref)
                ext = base_image.get("ext", "png")
                out_path = out_dir / f"page_{page_number + 1}_img_{img_idx + 1}.{ext}"
                out_path.write_bytes(base_image["image"])
                saved.append(str(out_path))
            except Exception as e:
                logger.warning(
                    f"Could not extract image {img_idx + 1} on page {page_number + 1} "
                    f"of {pdf_path.name}: {e}"
                )

        return saved

    # ---------------------------------------------------------
    # Step 8: Load a single PDF end-to-end
    # ---------------------------------------------------------
    def load_pdf(self, pdf_path: Path):
        documents = []

        pdf = self._open_pdf(pdf_path)
        if pdf is None:
            return documents

        plumber_pdf = None
        if self.enable_tables:
            try:
                plumber_pdf = pdfplumber.open(pdf_path)
            except Exception as e:
                logger.warning(f"pdfplumber could not open {pdf_path.name} for tables: {e}")

        total_pages = len(pdf)
        logger.info(f"Loading {pdf_path.name} ({total_pages} pages)")

        empty_pages = 0
        ocr_pages = 0
        equation_pages = 0

        for page_number in tqdm(range(total_pages), desc=pdf_path.name, leave=False):
            page = pdf[page_number]

            text = self._extract_native_text(page)
            extraction_method = "native"
            is_scanned = len(text.strip()) < MIN_TEXT_LENGTH_FOR_NATIVE

            if is_scanned:
                if self.enable_equation_ocr:
                    ocr_text = self._ocr_equation_page(page)
                else:
                    ocr_text = self._ocr_page(page)
                if ocr_text:
                    text = ocr_text
                    extraction_method = "ocr"
                    ocr_pages += 1

            has_equations = self._has_equations(text)
            if has_equations:
                equation_pages += 1

            table_text = self._extract_tables_for_page(plumber_pdf, page_number)
            has_tables = bool(table_text)
            if table_text:
                text = f"{text}\n{table_text}"

            figure_paths = self._extract_figures(pdf, page, pdf_path, page_number)

            if not text.strip():
                empty_pages += 1
                logger.warning(f"{pdf_path.name} Page {page_number + 1} is empty (native + OCR + tables all failed)")
                continue

            text = clean_text(text)

            metadata = {
                "source": pdf_path.name,
                "page": page_number + 1,
                "total_pages": total_pages,
                "source_type": "pdf",  # lets ChunkCleaner apply PDF-only front-matter stripping
                "file_path": str(pdf_path),
                "extraction_method": extraction_method,
                "has_tables": has_tables,
                "has_equations": has_equations,
                "has_images": bool(figure_paths),
                "image_count": len(figure_paths),
                "image_paths": figure_paths,
            }

            documents.append(Document(page_content=text, metadata=metadata))

        pdf.close()
        if plumber_pdf:
            plumber_pdf.close()

        logger.info(
            f"Loaded {len(documents)} pages from {pdf_path.name} "
            f"(OCR: {ocr_pages}, equation-flagged: {equation_pages}, empty skipped: {empty_pages})"
        )

        return documents

    # ---------------------------------------------------------
    # Step 9: Load every PDF, never let one bad file kill the batch
    # ---------------------------------------------------------
    def load_all_pdfs(self):
        all_documents = []
        pdf_files = self.get_pdf_files()

        for pdf_file in pdf_files:
            try:
                docs = self.load_pdf(pdf_file)
                all_documents.extend(docs)
            except Exception as e:
                logger.error(f"Unhandled error loading {pdf_file.name}: {e}")
                continue

        logger.info(f"Total Documents Loaded: {len(all_documents)}")
        return all_documents


if __name__ == "__main__":
    # Default run: no equation OCR (keeps it simple / lightweight).
    # Flip enable_equation_ocr=True only if your PDFs have scanned formulas
    # you actually need converted to LaTeX (requires: pip install pix2tex torch).
    loader = PDFLoader(DATA_DIR)
    docs = loader.load_all_pdfs()
    print(f"Loaded {len(docs)} documents total")
    for d in docs[:3]:
        print(d.metadata)
        print(d.page_content[:200])
        print("---")