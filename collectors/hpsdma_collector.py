"""
hpsdma_collector.py
--------------------
Collector for the HPSDMA (Himachal Pradesh State Disaster Management
Authority) annual disaster report PDFs — part of the `disaster_history`
digital-twin domain.

No API is available for this source, so reports are discovered by crawling
the public HPSDMA website (https://hpsdma.nic.in) and scraping PDF links
from its "Reports" section pages.

Behaviour highlights
---------------------
- Reads all settings from `config/config.yaml` (paths, HTTP/retry policy,
  download concurrency knobs, logging config).
- Discovers report links by crawling one or more entry pages (configurable)
  to a shallow depth, collecting `.pdf` links and tagging each with a year
  (2005-2025) parsed from the link text/URL where possible.
- If the HPSDMA website is unreachable (DNS failure, timeout, 4xx/5xx after
  retries), the failure is logged and any partially-discovered links plus
  the entry URLs are written to a `pending_retry.json` queue for a later
  run — the script exits cleanly instead of crashing.
- Downloads are streamed to disk, skip files that already exist, retry
  transient failures with exponential backoff, and are verified by file
  size before being marked complete.
- A `metadata.json` manifest and a per-run log file are always written.

Directory layout produced under `datasets/digital_twin/disaster_history/HPSDMA/`:
    raw/            downloaded PDF reports
    cleaned/        reserved for downstream text-extraction/cleaning steps
    logs/           per-run log files + pending_retry.json
    metadata.json   manifest of every discovered/downloaded report

Modular functions:
    fetch_report_links()  -> discover report PDF links from the website
    download_report()     -> download a single PDF with retry + skip logic
    save_metadata()        -> persist the manifest to metadata.json
    main()                  -> orchestrate the full run

Usage:
    python hpsdma_collector.py
    python hpsdma_collector.py --config config/config.yaml -v
    python hpsdma_collector.py --retry-only        # only re-attempt the pending queue
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse

import ssl

import requests
import urllib3
import yaml
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from tqdm import tqdm

try:
    from curl_cffi import requests as curl_requests
    from curl_cffi.requests.exceptions import RequestException as CurlRequestException
    CURL_CFFI_AVAILABLE = True
except ImportError:
    CURL_CFFI_AVAILABLE = False
    CurlRequestException = None  # type: ignore[assignment]

# Exceptions that mean "network/transport problem" regardless of which HTTP
# backend (plain requests, or curl_cffi when installed) is in use.
NETWORK_EXCEPTIONS: tuple = (requests.exceptions.RequestException,)
if CURL_CFFI_AVAILABLE:
    NETWORK_EXCEPTIONS = NETWORK_EXCEPTIONS + (CurlRequestException,)

# --------------------------------------------------------------------------- #
# Constants / defaults
# --------------------------------------------------------------------------- #
# This script lives in `collectors/hpsdma_collector.py`, one level below the
# project root where `config/config.yaml` actually sits. Resolve relative to
# the script's own location (not the current working directory) so it works
# the same whether launched from the project root, from collectors/, or via
# an IDE "Run" button.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"

DEFAULT_BASE_URL = "https://hpsdma.nic.in"
DEFAULT_ENTRY_URLS = [
    # HPSDMA "Reports -> Annual Activity Report" listing page.
    "https://hpsdma.nic.in/index1.aspx?lsid=5105&lev=2&lid=5003&langid=1",
    "https://hpsdma.nic.in",
]
REPORT_KEYWORDS = ("annual", "activity report", "disaster report", "report")
YEAR_PATTERN = re.compile(r"(20[0-2][0-9])")
MIN_YEAR, MAX_YEAR = 2005, 2025

USER_AGENT = (
    "Mozilla/5.0 (Himachal-Climate-Digital-Twin/1.0; "
    "+research-data-collector; contact: project-owner)"
)

logger = logging.getLogger("hpsdma_collector")


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
@dataclass
class ReportLink:
    """A single discovered (or downloaded) HPSDMA report."""

    url: str
    title: str
    year: int | None
    filename: str
    status: str = "discovered"          # discovered | downloaded | skipped | failed
    size_bytes: int | None = None
    sha256: str | None = None
    source_page: str | None = None
    downloaded_at: str | None = None
    error: str | None = None


# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
def configure_logging(log_dir: Path, level: str = "INFO", verbose: bool = False) -> None:
    """
    Configure console + rotating-style file logging for this run.

    Falls back gracefully if the project's shared logger module isn't
    importable — this script is designed to work standalone as well as
    inside the larger project.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    log_level = logging.DEBUG if verbose else getattr(logging, level.upper(), logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s", "%Y-%m-%d %H:%M:%S"
    )

    logger.setLevel(log_level)
    logger.handlers.clear()

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    logger.addHandler(console)

    log_file = log_dir / f"hpsdma_collector_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    logger.debug("Logging initialized. Log file: %s", log_file)

    # Try to piggyback on the project's shared logger config/utility, if present.
    try:
        from utils.logger import get_logger  # type: ignore

        logger.debug("Project logger utility found (utils.logger); using stdlib logger '%s' "
                      "configured above for consistency.", logger.name)
    except ImportError:
        logger.debug("No project-level utils.logger module found; using standalone logging setup.")


# --------------------------------------------------------------------------- #
# Config loading
# --------------------------------------------------------------------------- #
def load_config(config_path: Path) -> dict[str, Any]:
    """
    Load and lightly validate the master YAML config.

    Raises:
        FileNotFoundError: if the config file does not exist.
        ValueError: if the YAML cannot be parsed.
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    try:
        with config_path.open("r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Failed to parse YAML config at {config_path}: {exc}") from exc

    return config


def get_hpsdma_settings(config: dict[str, Any]) -> dict[str, Any]:
    """Extract HPSDMA-specific settings from the master config, with safe fallbacks."""
    dt_sources = config.get("digital_twin_sources", {}) or {}
    hpsdma_cfg = dt_sources.get("hpsdma", {}) or {}

    http_cfg = config.get("http", {}) or {}
    download_cfg = config.get("download", {}) or {}
    paths_cfg = config.get("paths", {}) or {}
    disaster_paths = paths_cfg.get("disaster_history", {}) if isinstance(paths_cfg, dict) else {}

    root_dir = Path(disaster_paths.get("hpsdma", "digital_twin/disaster_history/HPSDMA"))
    if not root_dir.is_absolute():
        root_dir = PROJECT_ROOT / root_dir

    return {
        "portal_url": hpsdma_cfg.get("portal_url", DEFAULT_BASE_URL),
        "entry_urls": hpsdma_cfg.get("entry_urls", DEFAULT_ENTRY_URLS),
        "crawl_depth": int(hpsdma_cfg.get("crawl_depth", 1)),
        "root_dir": root_dir,
        "timeout": int(http_cfg.get("timeout_seconds", 60)),
        "max_retries": int(http_cfg.get("max_retries", 5)),
        "backoff_factor": float(http_cfg.get("backoff_factor", 2.0)),
        "retry_on_status": set(http_cfg.get("retry_on_status", [429, 500, 502, 503, 504])),
        "verify_ssl": bool(hpsdma_cfg.get(
            "verify_ssl", http_cfg.get("verify_ssl", download_cfg.get("verify_ssl", True))
        )),
        "use_curl_cffi": bool(hpsdma_cfg.get("use_curl_cffi", True)),
        "chunk_size": int(download_cfg.get("chunk_size_bytes", 1_048_576)),
        "min_year": int(hpsdma_cfg.get("min_year", MIN_YEAR)),
        "max_year": int(hpsdma_cfg.get("max_year", MAX_YEAR)),
    }


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #
class LegacyTLSAdapter(HTTPAdapter):
    """
    HTTPS adapter that relaxes OpenSSL's default security level.

    Many older Indian .gov.in/.nic.in servers run TLS configurations
    (weak Diffie-Hellman params, older cipher orderings) that modern
    OpenSSL 3.x rejects outright under its default SECLEVEL=2 policy.
    That rejection commonly surfaces to Python not as a clear SSL error
    but as a bare `ConnectionResetError`. Lowering to SECLEVEL=1 restores
    compatibility with these older servers for a plain GET request; it
    does not disable certificate verification.
    """

    def init_poolmanager(self, *args: Any, **kwargs: Any) -> None:
        context = ssl.create_default_context()
        context.set_ciphers("DEFAULT:@SECLEVEL=1")
        kwargs["ssl_context"] = context
        super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, *args: Any, **kwargs: Any) -> Any:
        context = ssl.create_default_context()
        context.set_ciphers("DEFAULT:@SECLEVEL=1")
        kwargs["ssl_context"] = context
        return super().proxy_manager_for(*args, **kwargs)


def build_session(*, legacy_tls: bool = True, verify_ssl: bool = True, use_curl_cffi: bool = True) -> "requests.Session":
    """
    Create an HTTP session configured to look like a real browser visit.

    Government/NIC-hosted sites (like hpsdma.nic.in) commonly run WAF
    protection that resets connections (ConnectionResetError / WinError
    10054) for automated clients. This can happen at two different levels:

    1. Header-level fingerprinting -- fixed by sending a realistic browser
       header set (done below regardless of backend).
    2. TLS handshake fingerprinting (JA3) -- headers don't help here, since
       the block happens before any HTTP data is exchanged. Plain Python
       `requests`/OpenSSL produces a TLS ClientHello that looks nothing like
       a real browser's, no matter what headers are set afterward. If the
       `curl_cffi` package is installed, we use it here instead: it wraps
       curl-impersonate to reproduce a real Chrome TLS/HTTP2 fingerprint,
       which is usually what's needed to get past this class of block.

    If `curl_cffi` isn't installed, this transparently falls back to a
    plain `requests.Session` (optionally with `LegacyTLSAdapter` for older
    server TLS configs) -- the script still works, it just won't bypass a
    TLS-fingerprint-based block.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    if use_curl_cffi and CURL_CFFI_AVAILABLE:
        logger.debug("Using curl_cffi (Chrome TLS-fingerprint impersonation) for HTTP requests.")
        session = curl_requests.Session(impersonate="chrome124")
        session.headers.update(headers)
        return session

    if use_curl_cffi and not CURL_CFFI_AVAILABLE:
        logger.info(
            "curl_cffi not installed -- falling back to plain requests. If this site keeps "
            "resetting connections due to TLS fingerprint blocking, install it with "
            "`pip install curl_cffi` and re-run for a much better chance of success."
        )

    session = requests.Session()
    session.headers.update(headers)
    if legacy_tls and verify_ssl:
        session.mount("https://", LegacyTLSAdapter())
    return session


def warm_up_session(
    session: Any,
    base_url: str,
    *,
    timeout: int,
    verify_ssl: bool,
) -> None:
    """
    Make an initial visit to the site's homepage before crawling deeper pages.

    Many ASP.NET/NIC-hosted sites issue session cookies (and expect a
    Referer) on first contact; hitting a deep link cold is a common trigger
    for WAF connection resets. This is best-effort: failure here is logged
    but never raised, since fetch_page()'s own retry logic is the real
    source of truth for reachability.
    """
    try:
        response = session.get(base_url, timeout=timeout, verify=verify_ssl)
        logger.debug("Warm-up request to %s -> HTTP %s", base_url, response.status_code)
        if response.ok:
            session.headers["Referer"] = base_url
    except NETWORK_EXCEPTIONS as exc:
        logger.debug("Warm-up request to %s failed (non-fatal): %s", base_url, exc)


def fetch_page(
    url: str,
    session: Any,
    *,
    timeout: int,
    max_retries: int,
    backoff_factor: float,
    retry_on_status: set[int],
    verify_ssl: bool,
) -> BeautifulSoup | None:
    """
    Fetch a URL and parse it with BeautifulSoup, retrying transient failures.

    Returns:
        A BeautifulSoup object on success, or None if the page could not be
        fetched after all retries (network error, timeout, or a non-retryable
        / exhausted-retry HTTP status). Never raises for network-level issues
        -- callers should treat None as "this source is unavailable right now".
    """
    last_error: str | None = None

    for attempt in range(1, max_retries + 1):
        try:
            response = session.get(url, timeout=timeout, verify=verify_ssl)
            if response.status_code == 200:
                return BeautifulSoup(response.text, "html.parser")

            if response.status_code in retry_on_status:
                last_error = f"HTTP {response.status_code}"
                logger.warning(
                    "Attempt %d/%d: %s returned %s, retrying...",
                    attempt, max_retries, url, response.status_code,
                )
            else:
                logger.error("Failed to fetch %s: HTTP %s (not retryable)", url, response.status_code)
                return None

        except NETWORK_EXCEPTIONS as exc:
            last_error = str(exc)
            logger.warning("Attempt %d/%d: error fetching %s: %s", attempt, max_retries, url, exc)

        if attempt < max_retries:
            sleep_for = min(backoff_factor ** attempt, 15.0)
            time.sleep(sleep_for)

    logger.error("Giving up on %s after %d attempts. Last error: %s", url, max_retries, last_error)
    return None


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #
def _looks_like_report_link(href: str, text: str) -> bool:
    """Heuristic: does this link plausibly point at an annual/disaster report?"""
    href_l = href.lower()
    text_l = text.lower()
    if href_l.endswith(".pdf"):
        return True
    if "writereaddata" in href_l and (".pdf" in href_l):
        return True
    return any(keyword in text_l for keyword in REPORT_KEYWORDS)


def _extract_year(text: str, url: str, min_year: int, max_year: int) -> int | None:
    """Try to find a plausible report year in link text first, then the URL."""
    for candidate in (text, url):
        for match in YEAR_PATTERN.findall(candidate):
            year = int(match)
            if min_year <= year <= max_year:
                return year
    return None


def _safe_filename(title: str, url: str, year: int | None) -> str:
    """Build a filesystem-safe filename for a report."""
    stem_source = title.strip() or Path(urlparse(url).path).stem or "hpsdma_report"
    stem = re.sub(r"[^\w\-]+", "_", stem_source).strip("_")[:80] or "hpsdma_report"
    prefix = f"{year}_" if year else ""
    return f"{prefix}{stem}.pdf"


def fetch_report_links(
    entry_urls: Iterable[str],
    session: Any,
    *,
    crawl_depth: int,
    timeout: int,
    max_retries: int,
    backoff_factor: float,
    retry_on_status: set[int],
    verify_ssl: bool,
    min_year: int,
    max_year: int,
) -> tuple[list[ReportLink], bool]:
    """
    Discover HPSDMA annual disaster report PDF links.

    Crawls each entry URL (and, up to `crawl_depth` hops, same-domain pages
    linked from it whose link text looks report-related) collecting `.pdf`
    links.

    Returns:
        A tuple of (discovered_reports, site_reachable). `site_reachable` is
        False only when *every* entry URL failed to load at all, which the
        caller should treat as "the HPSDMA website is currently unavailable".
    """
    visited_pages: set[str] = set()
    discovered: dict[str, ReportLink] = {}  # keyed by absolute PDF URL, dedups
    any_entry_reachable = False

    queue: list[tuple[str, int]] = [(url, 0) for url in entry_urls]
    base_netloc = urlparse(next(iter(entry_urls), DEFAULT_BASE_URL)).netloc

    while queue:
        page_url, depth = queue.pop(0)
        if page_url in visited_pages:
            continue
        visited_pages.add(page_url)

        logger.info("Scanning page (depth %d): %s", depth, page_url)
        soup = fetch_page(
            page_url,
            session,
            timeout=timeout,
            max_retries=max_retries,
            backoff_factor=backoff_factor,
            retry_on_status=retry_on_status,
            verify_ssl=verify_ssl,
        )
        if soup is None:
            logger.warning("Could not load page, skipping: %s", page_url)
            continue

        any_entry_reachable = True
        next_hop_candidates: list[str] = []

        if queue:
            time.sleep(1.0)  # politeness delay between page fetches, avoids rapid-fire WAF triggers

        for anchor in soup.find_all("a", href=True):
            href = anchor["href"].strip()
            text = anchor.get_text(strip=True)
            if not href or href.startswith("javascript:") or href.startswith("#"):
                continue

            absolute_url = urljoin(page_url, href)
            parsed = urlparse(absolute_url)
            if parsed.netloc and parsed.netloc != base_netloc:
                continue  # stay on-domain

            if absolute_url.lower().endswith(".pdf") or "writereaddata" in absolute_url.lower():
                if _looks_like_report_link(absolute_url, text):
                    year = _extract_year(text, absolute_url, min_year, max_year)
                    if absolute_url not in discovered:
                        title = text or Path(parsed.path).stem
                        discovered[absolute_url] = ReportLink(
                            url=absolute_url,
                            title=title,
                            year=year,
                            filename=_safe_filename(title, absolute_url, year),
                            source_page=page_url,
                        )
            elif depth < crawl_depth and _looks_like_report_link(absolute_url, text):
                next_hop_candidates.append(absolute_url)

        for candidate in next_hop_candidates:
            if candidate not in visited_pages:
                queue.append((candidate, depth + 1))

    reports = sorted(
        discovered.values(),
        key=lambda r: (r.year is None, r.year or 0, r.title),
    )
    logger.info("Discovery complete: %d candidate report link(s) found.", len(reports))
    return reports, any_entry_reachable


# --------------------------------------------------------------------------- #
# Download
# --------------------------------------------------------------------------- #
def _sha256_of_file(path: Path, chunk_size: int = 1_048_576) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_report(
    report: ReportLink,
    dest_dir: Path,
    session: Any,
    *,
    timeout: int,
    max_retries: int,
    backoff_factor: float,
    retry_on_status: set[int],
    verify_ssl: bool,
    chunk_size: int,
    overwrite: bool = False,
) -> ReportLink:
    """
    Download a single report PDF to `dest_dir`, with retry and skip-if-exists.

    Mutates and returns the given `ReportLink` with an updated status
    (`downloaded`, `skipped`, or `failed`) plus size/hash/error metadata.
    Never raises -- all failures are captured on the returned object so the
    overall run can continue past individual bad reports.
    """
    dest_path = dest_dir / report.filename

    if dest_path.exists() and not overwrite:
        report.status = "skipped"
        report.size_bytes = dest_path.stat().st_size
        logger.debug("Already downloaded, skipping: %s", dest_path.name)
        return report

    tmp_path = dest_path.with_suffix(dest_path.suffix + ".part")
    last_error: str | None = None

    for attempt in range(1, max_retries + 1):
        try:
            with session.get(report.url, stream=True, timeout=timeout, verify=verify_ssl) as response:
                if response.status_code != 200:
                    if response.status_code in retry_on_status:
                        last_error = f"HTTP {response.status_code}"
                        logger.warning(
                            "Attempt %d/%d: %s -> HTTP %s, retrying...",
                            attempt, max_retries, report.filename, response.status_code,
                        )
                        time.sleep(backoff_factor ** attempt)
                        continue
                    report.status = "failed"
                    report.error = f"HTTP {response.status_code}"
                    logger.error("Download failed (non-retryable) for %s: HTTP %s",
                                 report.filename, response.status_code)
                    return report

                content_type = response.headers.get("Content-Type", "")
                if "pdf" not in content_type.lower() and "octet-stream" not in content_type.lower():
                    logger.warning(
                        "Unexpected Content-Type '%s' for %s -- saving anyway, verify manually.",
                        content_type, report.filename,
                    )

                with tmp_path.open("wb") as f:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)

            tmp_path.rename(dest_path)
            report.status = "downloaded"
            report.size_bytes = dest_path.stat().st_size
            report.sha256 = _sha256_of_file(dest_path)
            report.downloaded_at = datetime.now(timezone.utc).isoformat()
            logger.info("Downloaded: %s (%.1f KB)", report.filename, report.size_bytes / 1024)
            return report

        except NETWORK_EXCEPTIONS as exc:
            last_error = str(exc)
            logger.warning("Attempt %d/%d: error downloading %s: %s",
                            attempt, max_retries, report.filename, exc)
            if attempt < max_retries:
                time.sleep(backoff_factor ** attempt)
        finally:
            if tmp_path.exists() and not dest_path.exists():
                pass  # keep partial file for potential resume/debug; cleaned up below on final failure

    if tmp_path.exists():
        tmp_path.unlink(missing_ok=True)

    report.status = "failed"
    report.error = last_error or "Unknown download error"
    logger.error("Giving up on %s after %d attempts: %s", report.filename, max_retries, report.error)
    return report


# --------------------------------------------------------------------------- #
# Metadata / retry-queue persistence
# --------------------------------------------------------------------------- #
def save_metadata(reports: list[ReportLink], metadata_path: Path) -> None:
    """Write the full manifest of discovered/downloaded reports to metadata.json."""
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": "HPSDMA",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_reports": len(reports),
        "reports": [asdict(r) for r in reports],
    }
    try:
        with metadata_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        logger.info("Saved metadata for %d report(s) -> %s", len(reports), metadata_path)
    except OSError as exc:
        logger.error("Failed to write metadata file %s: %s", metadata_path, exc)


def save_pending_retry(entry_urls: list[str], reports: list[ReportLink], pending_path: Path) -> None:
    """
    Persist a retry queue when the site was unreachable or some reports failed.

    This is what lets a later run pick up where this one left off instead of
    re-crawling from scratch or losing track of partial progress.
    """
    pending_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "entry_urls_to_retry": entry_urls,
        "failed_reports": [asdict(r) for r in reports if r.status == "failed"],
    }
    try:
        with pending_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        logger.info(
            "Saved retry queue (%d entry URL(s), %d failed report(s)) -> %s",
            len(entry_urls), len(payload["failed_reports"]), pending_path,
        )
    except OSError as exc:
        logger.error("Failed to write pending retry file %s: %s", pending_path, exc)


def load_pending_retry(pending_path: Path) -> dict[str, Any]:
    """Load a previously saved retry queue, if any."""
    if not pending_path.exists():
        return {}
    try:
        with pending_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read existing pending retry file %s: %s", pending_path, exc)
        return {}


# --------------------------------------------------------------------------- #
# CLI / orchestration
# --------------------------------------------------------------------------- #
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect HPSDMA annual disaster report PDFs.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH,
                         help=f"Path to config.yaml (default: {DEFAULT_CONFIG_PATH})")
    parser.add_argument("--retry-only", action="store_true",
                         help="Only re-attempt entry URLs / reports from a previous pending_retry.json.")
    parser.add_argument("--overwrite", action="store_true",
                         help="Re-download reports even if a local file already exists.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        config = load_config(args.config)
    except (FileNotFoundError, ValueError) as exc:
        print(f"FATAL: could not load config: {exc}", file=sys.stderr)
        return 1

    settings = get_hpsdma_settings(config)
    if not settings["verify_ssl"]:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    root_dir: Path = settings["root_dir"]
    raw_dir = root_dir / "raw"
    cleaned_dir = root_dir / "cleaned"
    logs_dir = root_dir / "logs"
    metadata_path = root_dir / "metadata.json"
    pending_path = logs_dir / "pending_retry.json"

    for d in (raw_dir, cleaned_dir, logs_dir):
        d.mkdir(parents=True, exist_ok=True)

    log_cfg = config.get("logging", {}) or {}
    configure_logging(logs_dir, level=log_cfg.get("level", "INFO"), verbose=args.verbose)

    if not settings["verify_ssl"]:
        logger.warning(
            "SSL certificate verification is DISABLED for HPSDMA requests "
            "(verify_ssl: false in config). Traffic is still encrypted, but the "
            "server's certificate chain is not being validated -- only use this "
            "if you've confirmed hpsdma.nic.in's certificate is the source of "
            "connection failures, and trust the network path to the site."
        )

    logger.info("=" * 70)
    logger.info("HPSDMA Annual Disaster Report Collector — starting run")
    logger.info("Portal      : %s", settings["portal_url"])
    logger.info("Raw dir     : %s", raw_dir)
    logger.info("Year range  : %d - %d", settings["min_year"], settings["max_year"])
    logger.info(
        "HTTP backend: %s",
        "curl_cffi (Chrome TLS impersonation)"
        if (settings["use_curl_cffi"] and CURL_CFFI_AVAILABLE)
        else "requests (curl_cffi not installed or disabled)",
    )
    logger.info("=" * 70)

    session = build_session(verify_ssl=settings["verify_ssl"], use_curl_cffi=settings["use_curl_cffi"])
    warm_up_session(session, settings["portal_url"], timeout=settings["timeout"], verify_ssl=settings["verify_ssl"])

    entry_urls = list(settings["entry_urls"])
    if args.retry_only:
        pending = load_pending_retry(pending_path)
        entry_urls = pending.get("entry_urls_to_retry", entry_urls) or entry_urls
        logger.info("Retry-only mode: using %d entry URL(s) from pending queue.", len(entry_urls))

    reports, site_reachable = fetch_report_links(
        entry_urls,
        session,
        crawl_depth=settings["crawl_depth"],
        timeout=settings["timeout"],
        max_retries=settings["max_retries"],
        backoff_factor=settings["backoff_factor"],
        retry_on_status=settings["retry_on_status"],
        verify_ssl=settings["verify_ssl"],
        min_year=settings["min_year"],
        max_year=settings["max_year"],
    )

    if not site_reachable:
        logger.error(
            "HPSDMA website appears to be unavailable (all %d entry URL(s) failed to load). "
            "Saving entry URLs for retry instead of crashing.",
            len(entry_urls),
        )
        save_pending_retry(entry_urls, reports, pending_path)
        save_metadata(reports, metadata_path)  # persist whatever was known before, unchanged
        logger.info("Run ended early. Re-run this script later (or with --retry-only) to try again.")
        return 0  # graceful exit, not a crash

    if not reports:
        logger.warning("Site was reachable but no report links were discovered. "
                        "The page structure may have changed -- consider updating "
                        "REPORT_KEYWORDS / entry_urls in config.")
        save_metadata(reports, metadata_path)
        return 0

    logger.info("Downloading %d discovered report(s)...", len(reports))
    results: list[ReportLink] = []
    counts = {"downloaded": 0, "skipped": 0, "failed": 0}

    for report in tqdm(reports, desc="HPSDMA reports", unit="pdf"):
        updated = download_report(
            report,
            raw_dir,
            session,
            timeout=settings["timeout"],
            max_retries=settings["max_retries"],
            backoff_factor=settings["backoff_factor"],
            retry_on_status=settings["retry_on_status"],
            verify_ssl=settings["verify_ssl"],
            chunk_size=settings["chunk_size"],
            overwrite=args.overwrite,
        )
        results.append(updated)
        counts[updated.status] = counts.get(updated.status, 0) + 1

    save_metadata(results, metadata_path)

    failed_reports = [r for r in results if r.status == "failed"]
    if failed_reports:
        save_pending_retry([], failed_reports, pending_path)
    elif pending_path.exists():
        pending_path.unlink(missing_ok=True)  # clear a stale queue once everything succeeds

    logger.info("=" * 70)
    logger.info("RUN SUMMARY")
    logger.info("  Discovered : %d", len(results))
    logger.info("  Downloaded : %d", counts.get("downloaded", 0))
    logger.info("  Skipped    : %d (already present)", counts.get("skipped", 0))
    logger.info("  Failed     : %d", counts.get("failed", 0))
    logger.info("  Metadata   : %s", metadata_path)
    if failed_reports:
        logger.info("  Retry queue: %s", pending_path)
    logger.info("=" * 70)

    return 0 if not failed_reports else 2


if __name__ == "__main__":
    raise SystemExit(main())