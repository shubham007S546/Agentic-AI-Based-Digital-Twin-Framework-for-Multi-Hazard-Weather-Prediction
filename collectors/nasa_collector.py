"""
collectors/nasa_collector_fast.py
══════════════════════════════════════════════════════════════════════════════
NASA GPM IMERG Half-Hourly Downloader — HIGH SPEED VERSION

WHAT CHANGED vs. the original (and why it was slow)
────────────────────────────────────────────────────
  SLOW 1 — Date range 2015–2025 (4,018 days × 48 files = ~192,000 files)
    FIX   : Default range is now 2022-01-01 → 2024-09-30 (your actual project
            period). That's ~1,095 days = ~52,560 files — 3.7× fewer files
            before touching a single line of download logic.

  SLOW 2 — 6 concurrent downloads per day (sequential day loop on top of that)
    FIX   : All files across ALL days are queued into a single async pool
            with MAX_CONCURRENT=25 simultaneous HTTPS connections. On a
            reasonable broadband connection this gives ~10–15× speedup over
            the original approach.

  SLOW 3 — No skip-if-exists check, so re-runs re-download everything
    FIX   : Any file that already exists on disk AND has size > 1 KB is
            skipped immediately. This makes interrupted runs resumable
            at zero cost — just re-run the script.

  SLOW 4 — Synchronous requests inside a thread pool
    FIX   : Pure asyncio + aiohttp — no thread overhead, true async I/O,
            much better CPU utilisation at high concurrency.

SPEED ESTIMATE (approximate, depends on your connection and NASA server load)
──────────────────────────────────────────────────────────────────────────────
  Original   :  6 concurrent, ~192k files  → days–weeks
  This script:  25 concurrent, ~52k files  → 3–8 hours on 50 Mbps+

INSTALL
───────
  pip install aiohttp aiofiles tqdm pyyaml

USAGE
─────
  python nasa_collector_fast.py
  python nasa_collector_fast.py --start 2022-01-01 --end 2024-09-30 --workers 25
  python nasa_collector_fast.py --workers 40   # if NASA doesn't rate-limit you

NASA EARTHDATA LOGIN
──────────────────────
  Credentials are read, in this priority order:
    1. --user / --password CLI args (if passed)
    2. EARTHDATA_USER / EARTHDATA_PASS environment variables (if set)
    3. config.yaml -> api_keys.nasa_username / api_keys.nasa_password
       (your project's existing config file -- this is now the default,
       no env vars needed if config.yaml is already filled in)
    4. ~/.netrc (if none of the above are set, aiohttp falls back to this)

  Register free at: https://urs.earthdata.nasa.gov/
"""
from __future__ import annotations
import argparse
import asyncio
import os
import sys
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Optional
import aiohttp
import aiofiles
import yaml
from tqdm.asyncio import tqdm as async_tqdm

# ──────────────────────────────────────────────────────────────
#  CONFIG.YAML LOADING  (credentials + date range, per your project layout)
# ──────────────────────────────────────────────────────────────

def load_config(config_path: Path) -> dict:
    """
    Reads config.yaml (created alongside config.example.yaml in your repo).
    Falls back gracefully if the file or keys are missing -- env vars /
    --start/--end/--user/--password CLI args still work as an override.
    """
    if not config_path.exists():
        print(f"  NOTE: {config_path} not found -- falling back to env vars / CLI args only.")
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    return cfg


# ──────────────────────────────────────────────────────────────
#  CONFIGURATION  (edit here or use CLI args)
# ──────────────────────────────────────────────────────────────

DEFAULT_START      = "2022-01-01"     # ← YOUR project start (was 2015 before)
DEFAULT_END        = "2024-09-30"     # ← YOUR project end
DEFAULT_WORKERS    = 25               # simultaneous downloads (safe for NASA)
DEFAULT_CHUNK_SIZE = 1024 * 256       # 256 KB read buffer per download
MIN_VALID_SIZE_KB  = 1                # files smaller than this are re-downloaded

# NASA GES DISC CMR API — finds the actual download URLs for each granule
CMR_SEARCH_URL = (
    "https://cmr.earthdata.nasa.gov/search/granules.json"
    "?short_name=GPM_3IMERGHHL"
    "&version=07"
    "&temporal[]={start}T00:00:00Z,{end}T23:59:59Z"
    "&bounding_box=76.5,31.35,77.5,32.1"       # Mandi district bbox
    "&page_size=2000"
    "&page_num={page}"
)
EARTHDATA_LOGIN_URL = "https://urs.earthdata.nasa.gov"


# ──────────────────────────────────────────────────────────────
#  DATA CLASS
# ──────────────────────────────────────────────────────────────

@dataclass
class Granule:
    url: str
    filename: str
    date_str: str   # YYYY-MM-DD, for organising into subdirs


# ──────────────────────────────────────────────────────────────
#  CMR GRANULE DISCOVERY (async)
# ──────────────────────────────────────────────────────────────

async def discover_granules(
    session: aiohttp.ClientSession,
    start: date,
    end: date,
    output_dir: Path,
) -> list[Granule]:
    """
    Query NASA CMR for all GPM IMERG half-hourly granules in the date range.
    CMR returns paged JSON (up to 2000 results/page); we iterate all pages.
    This replaces the per-day CMR call in the original collector with a
    single bulk query — typically ~2–3 API calls for a 3-year period
    instead of ~1095 individual calls.
    """
    granules: list[Granule] = []
    page = 1
    print(f"  Discovering granules via CMR ({start} → {end})...")

    while True:
        url = CMR_SEARCH_URL.format(
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            page=page,
        )
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
            if resp.status != 200:
                print(f"  WARNING: CMR returned HTTP {resp.status} on page {page}")
                break
            data = await resp.json()

        entries = data.get("feed", {}).get("entry", [])
        if not entries:
            break

        for entry in entries:
            for link in entry.get("links", []):
                href = link.get("href", "")
                if href.endswith(".HDF5") and "3B-HHR" in href:
                    fname = href.split("/")[-1]
                    # Extract date from filename: 3B-HHR*.YYYYMMDD-S*.HDF5
                    try:
                        date_part = [p for p in fname.split(".") if len(p) == 8 and p.isdigit()][0]
                        d_str = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]}"
                    except (IndexError, ValueError):
                        d_str = "unknown"
                    granules.append(Granule(url=href, filename=fname, date_str=d_str))
                    break

        print(f"    Page {page}: {len(entries)} entries found ({len(granules)} total so far)")
        if len(entries) < 2000:
            break
        page += 1

    print(f"  Total granules discovered: {len(granules):,}")
    return granules


# ──────────────────────────────────────────────────────────────
#  SINGLE FILE DOWNLOADER (async)
# ──────────────────────────────────────────────────────────────

async def download_one(
    session: aiohttp.ClientSession,
    granule: Granule,
    output_dir: Path,
    semaphore: asyncio.Semaphore,
    chunk_size: int,
    stats: dict,
    max_retries: int = 5,
    backoff_factor: float = 2.0,
    retry_on_status: tuple[int, ...] = (429, 500, 502, 503, 504),
    timeout_seconds: int = 120,
) -> None:
    """
    Download a single HDF5 granule. Skips if the file already exists
    and is larger than MIN_VALID_SIZE_KB (resume support).

    Retries with exponential backoff on transient failures (429 rate-limit,
    5xx server errors) instead of just marking the file failed -- this
    matters more than raw concurrency for total wall-clock time: without
    it, every 429 becomes a file you have to manually re-run the whole
    script to retry, and pushing workers higher just makes 429s MORE
    likely, not less. Reads retry policy from config.yaml's http: section
    if available (falls back to sane defaults otherwise).
    """
    # Organise into per-day subdirs: output_dir/YYYY/MM/YYYY-MM-DD/file.HDF5
    if granule.date_str != "unknown":
        year, month = granule.date_str[:4], granule.date_str[5:7]
        dest_dir = output_dir / year / month / granule.date_str
    else:
        dest_dir = output_dir / "unknown"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / granule.filename

    # ── Skip if already downloaded ──
    if dest_path.exists() and dest_path.stat().st_size > MIN_VALID_SIZE_KB * 1024:
        stats["skipped"] += 1
        return

    async with semaphore:
        for attempt in range(max_retries + 1):
            try:
                async with session.get(
                    granule.url,
                    timeout=aiohttp.ClientTimeout(total=timeout_seconds, connect=30),
                    allow_redirects=True,
                ) as resp:
                    if resp.status == 200:
                        async with aiofiles.open(dest_path, "wb") as f:
                            async for chunk in resp.content.iter_chunked(chunk_size):
                                await f.write(chunk)
                        stats["downloaded"] += 1
                        stats["bytes"] += dest_path.stat().st_size
                        return
                    elif resp.status == 401:
                        stats["auth_errors"] += 1
                        stats["failed"] += 1
                        if stats["auth_errors"] == 1:
                            print(
                                "\n  AUTH ERROR (401): NASA Earthdata login failed.\n"
                                "  Check nasa_username / nasa_password in config.yaml,\n"
                                "  or EARTHDATA_USER / EARTHDATA_PASS env vars.\n"
                                "  Register free at: https://urs.earthdata.nasa.gov/\n"
                            )
                        return   # not retryable -- wrong credentials won't fix themselves
                    elif resp.status in retry_on_status and attempt < max_retries:
                        wait = backoff_factor ** attempt
                        stats["retries"] += 1
                        await asyncio.sleep(wait)
                        continue   # retry
                    else:
                        stats["failed"] += 1
                        return
            except asyncio.TimeoutError:
                if attempt < max_retries:
                    stats["retries"] += 1
                    await asyncio.sleep(backoff_factor ** attempt)
                    continue
                stats["failed"] += 1
                if dest_path.exists():
                    dest_path.unlink()
                return
            except Exception:
                stats["failed"] += 1
                if dest_path.exists():
                    dest_path.unlink()
                return


# ──────────────────────────────────────────────────────────────
#  MAIN ASYNC RUNNER
# ──────────────────────────────────────────────────────────────

async def run(
    start: date,
    end: date,
    output_dir: Path,
    max_workers: int,
    chunk_size: int,
    earthdata_user: Optional[str],
    earthdata_pass: Optional[str],
    max_retries: int = 5,
    backoff_factor: float = 2.0,
    retry_on_status: tuple[int, ...] = (429, 500, 502, 503, 504),
    timeout_seconds: int = 120,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(max_workers)

    stats = {
        "downloaded": 0,
        "skipped": 0,
        "failed": 0,
        "auth_errors": 0,
        "retries": 0,
        "bytes": 0,
    }

    # NASA Earthdata requires Basic Auth on the actual data server,
    # but the redirect chain (CMR → pps.gsfc.nasa.gov → urs.earthdata.nasa.gov)
    # is handled by passing credentials as BasicAuth to aiohttp.
    auth = None
    if earthdata_user and earthdata_pass:
        auth = aiohttp.BasicAuth(earthdata_user, earthdata_pass)
    else:
        print(
            "  WARNING: No NASA Earthdata credentials found (checked config.yaml,\n"
            "  env vars, and CLI args). Downloads will likely fail with 401 unless\n"
            "  you have a ~/.netrc file.\n"
        )

    connector = aiohttp.TCPConnector(
        limit=max_workers + 5,   # slightly above semaphore so connector isn't the bottleneck
        ttl_dns_cache=300,
        ssl=True,
    )

    async with aiohttp.ClientSession(
        connector=connector,
        auth=auth,
        headers={"User-Agent": "GPM-IMERG-Downloader/2.0 (research project)"},
    ) as session:

        # ── Step 1: Discover all granule URLs via CMR ──
        granules = await discover_granules(session, start, end, output_dir)

        if not granules:
            print("  No granules found. Check date range, bbox, and CMR availability.")
            return

        already_done = sum(
            1 for g in granules
            if (output_dir / g.date_str[:4] / g.date_str[5:7] / g.date_str / g.filename).exists()
            and (output_dir / g.date_str[:4] / g.date_str[5:7] / g.date_str / g.filename).stat().st_size
               > MIN_VALID_SIZE_KB * 1024
        )
        to_download = len(granules) - already_done
        print(f"\n  {len(granules):,} total granules | {already_done:,} already on disk | "
              f"{to_download:,} to download")
        print(f"  Concurrency : {max_workers} parallel downloads")
        print(f"  Output dir  : {output_dir.resolve()}\n")

        if to_download == 0:
            print("  All files already downloaded. Nothing to do.")
            return

        # ── Step 2: Download everything in parallel ──
        t0 = time.perf_counter()
        tasks = [
            download_one(session, g, output_dir, semaphore, chunk_size, stats,
                         max_retries=max_retries, backoff_factor=backoff_factor,
                         retry_on_status=retry_on_status, timeout_seconds=timeout_seconds)
            for g in granules
        ]

        for coro in async_tqdm.as_completed(
            tasks,
            total=len(tasks),
            desc="Downloading",
            unit="file",
            dynamic_ncols=True,
        ):
            await coro

        elapsed = time.perf_counter() - t0

    # ── Summary ──
    total_mb = stats["bytes"] / (1024 ** 2)
    speed_mbps = total_mb / max(elapsed, 1)
    print(f"\n{'='*60}")
    print(f"  DOWNLOAD COMPLETE")
    print(f"{'='*60}")
    print(f"  Downloaded : {stats['downloaded']:,} files  ({total_mb:.0f} MB)")
    print(f"  Skipped    : {stats['skipped']:,} (already on disk)")
    print(f"  Retried    : {stats['retries']:,} requests (rate-limit/server-error backoff)")
    print(f"  Failed     : {stats['failed']:,}")
    print(f"  Time       : {elapsed/60:.1f} min  ({speed_mbps:.1f} MB/s avg)")
    print(f"  Output     : {output_dir.resolve()}")

    if stats["failed"] > 0:
        print(f"\n  {stats['failed']} files failed. Re-run the script to retry them —")
        print(f"  completed files are skipped automatically (resume support).")

    if stats["auth_errors"] > 0:
        print(f"\n  {stats['auth_errors']} files failed with 401 (auth error).")
        print(f"  Fix: set nasa_username / nasa_password in config.yaml, or")
        print(f"  EARTHDATA_USER / EARTHDATA_PASS environment variables.")


# ──────────────────────────────────────────────────────────────
#  ENTRY POINT
# ──────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Fast async NASA GPM IMERG downloader")
    parser.add_argument("--start",   default=None,
                        help=f"Start date YYYY-MM-DD (default: config.yaml dates.start_date, "
                             f"else {DEFAULT_START})")
    parser.add_argument("--end",     default=None,
                        help=f"End date YYYY-MM-DD (default: config.yaml dates.end_date, "
                             f"else {DEFAULT_END})")
    parser.add_argument("--output",  default=None,
                        help="Output directory (default: source_2_nasa_gpm/raw/)")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help=f"Parallel downloads (default: {DEFAULT_WORKERS}, max recommended: 40)")
    parser.add_argument("--config",  default=None,
                        help="Path to config.yaml (default: ../config/config.yaml relative to this script)")
    parser.add_argument("--user",     default=None, help="NASA Earthdata username (overrides config.yaml)")
    parser.add_argument("--password", default=None, help="NASA Earthdata password (overrides config.yaml)")
    args = parser.parse_args()

    # Resolve output dir relative to script location if not specified
    script_dir = Path(__file__).resolve().parent

    # ── Load config.yaml ──
    config_path = Path(args.config) if args.config else script_dir.parent / "config" / "config.yaml"
    cfg = load_config(config_path)
    cfg_dates = cfg.get("dates", {})
    cfg_nasa = cfg.get("sources", {}).get("nasa_gpm", {})
    cfg_api_keys = cfg.get("api_keys", {})
    cfg_http = cfg.get("http", {})

    if args.output:
        output_dir = Path(args.output)
    elif cfg_nasa.get("download_dir"):
        output_dir = (script_dir.parent / cfg_nasa["download_dir"] / "raw")
    else:
        candidate = script_dir.parent / "datasets" / "source_2_nasa_gpm" / "raw"
        output_dir = candidate if candidate.parent.parent.exists() else script_dir / "nasa_gpm_raw"

    # ── Resolve credentials: CLI > env vars > config.yaml > .netrc ──
    earthdata_user = args.user or os.environ.get("EARTHDATA_USER") or cfg_api_keys.get("nasa_username")
    earthdata_pass = args.password or os.environ.get("EARTHDATA_PASS") or cfg_api_keys.get("nasa_password")

    # Guard against the placeholder values still sitting in config.example.yaml
    placeholder_markers = ("ENTER_YOUR_", "YOUR_NASA")
    if earthdata_user and any(m in earthdata_user for m in placeholder_markers):
        earthdata_user = None
    if earthdata_pass and any(m in earthdata_pass for m in placeholder_markers):
        earthdata_pass = None

    netrc_path = Path.home() / ".netrc"
    if not earthdata_user and not netrc_path.exists():
        print(
            "\n  ╔══════════════════════════════════════════════════════════╗\n"
            "  ║  NASA EARTHDATA CREDENTIALS REQUIRED                     ║\n"
            "  ║                                                          ║\n"
            "  ║  Fill these in config.yaml under api_keys:                ║\n"
            "  ║    nasa_username: your_username                          ║\n"
            "  ║    nasa_password: your_password                          ║\n"
            "  ║                                                          ║\n"
            "  ║  Or pass --user / --password on the command line,        ║\n"
            "  ║  or set EARTHDATA_USER / EARTHDATA_PASS env vars.        ║\n"
            "  ║                                                          ║\n"
            "  ║  Register free at: https://urs.earthdata.nasa.gov/      ║\n"
            "  ╚══════════════════════════════════════════════════════════╝\n"
        )

    # ── Resolve date range: CLI > config.yaml > script defaults ──
    start_str = args.start or cfg_dates.get("start_date") or DEFAULT_START
    end_str   = args.end   or cfg_dates.get("end_date")   or DEFAULT_END
    start = date.fromisoformat(start_str)
    end   = date.fromisoformat(end_str)
    days  = (end - start).days + 1
    est_files = days * 48
    est_gb = est_files * 7.5 / 1024  # ~7.5 MB per HDF5 file average

    print("=" * 60)
    print("  NASA GPM IMERG FAST DOWNLOADER")
    print("=" * 60)
    print(f"  Config     : {config_path}  {'(found)' if config_path.exists() else '(not found -- using defaults)'}")
    print(f"  Date range : {start} → {end}  ({days:,} days)")
    print(f"  Est. files : ~{est_files:,}  (~{est_gb:.0f} GB)")
    print(f"  Workers    : {args.workers} concurrent downloads")
    print(f"  Credentials: {'from config.yaml' if (earthdata_user and cfg_api_keys.get('nasa_username') == earthdata_user) else ('from CLI/env' if earthdata_user else 'NOT SET -- relying on ~/.netrc')}")
    print(f"  Output     : {output_dir.resolve()}")
    print()

    if days > 365 * 3 + 1:
        print(f"  NOTE: You are downloading {days} days of data. Your project uses\n"
              f"  2022-01-01 → 2024-09-30 (~1,004 days). If you have already run\n"
              f"  this with a wider range and want to restart, pass:\n"
              f"    --start 2022-01-01 --end 2024-09-30\n"
              f"  This reduces files from ~{days*48:,} to ~{1004*48:,} (3.5x faster).\n")

    asyncio.run(run(
        start=start,
        end=end,
        output_dir=output_dir,
        max_workers=args.workers,
        chunk_size=DEFAULT_CHUNK_SIZE,
        earthdata_user=earthdata_user,
        earthdata_pass=earthdata_pass,
        max_retries=cfg_http.get("max_retries", 5),
        backoff_factor=cfg_http.get("backoff_factor", 2.0),
        retry_on_status=tuple(cfg_http.get("retry_on_status", [429, 500, 502, 503, 504])),
        timeout_seconds=cfg_http.get("timeout_seconds", 120),
    ))


if __name__ == "__main__":
    main()
    