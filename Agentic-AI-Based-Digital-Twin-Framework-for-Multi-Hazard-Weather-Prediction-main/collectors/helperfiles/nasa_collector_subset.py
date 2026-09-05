"""
collectors/nasa_collector_subset.py
══════════════════════════════════════════════════════════════════════════════
NASA GPM IMERG Half-Hourly Downloader — BBOX-SUBSET VERSION (v2: requests + .netrc)

WHY THIS VERSION SWITCHED FROM aiohttp TO requests FOR DOWNLOADS
────────────────────────────────────────────────────────────────
  v1 of this script used aiohttp end-to-end, hand-rolling NASA Earthdata's
  redirect-based login flow (data URL -> redirect to urs.earthdata.nasa.gov
  for login -> redirect back with an auth code -> exchange for a session
  cookie -> finally reach the data). In testing, that hand-rolled version
  got a real authorization code back from Earthdata Login but then looped
  forever instead of completing the final cookie handshake.

  This is a known, well-documented rough edge: NASA's own examples, and
  every community example found while debugging this, use `requests`
  (or curl/wget) with a `.netrc` file for this exact flow -- never a
  from-scratch async client. `requests` implements the redirect+cookie
  handling this dance depends on; re-implementing it correctly on top of
  aiohttp turned into a rabbit hole not worth the risk of silently
  producing corrupted downloads.

  So: CMR granule discovery (metadata-only, doesn't need login) stays on
  aiohttp/asyncio, since that part worked correctly. Actual file
  downloads switch to `requests.Session()` + a `.netrc` file, run
  concurrently via a ThreadPoolExecutor (the same proven pattern already
  used successfully in era5_collector.py).

WHAT THIS SCRIPT STILL DOES
─────────────────────────────
  Uses GES DISC's server-side subsetting service to request ONLY the
  Mandi bounding box + only the variables you need, per granule, instead
  of the full global grid. Each response is a few KB instead of ~7.5 MB,
  so total transfer for the whole project period is a few hundred MB
  instead of ~360 GB -- the actual reason this can finish in well under
  an hour once the auth flow works.

  SELF-TESTS on one real granule before committing to the full run:
    - ensures a working ~/.netrc entry for urs.earthdata.nasa.gov exists
      (creates/updates it automatically from config.yaml credentials)
    - downloads 1 sample subset
    - checks the response is actually valid NetCDF, not an HTML/XML error page
    - only proceeds to the bulk run if the sample passes

INSTALL
───────
  pip install requests aiohttp tqdm pyyaml

USAGE
─────
  python nasa_collector_subset.py                     # self-test, then full run
  python nasa_collector_subset.py --test-only          # just run the self-test
  python nasa_collector_subset.py --workers 20
  python nasa_collector_subset.py --variables precipitationCal,precipitationUncal

NASA EARTHDATA LOGIN
──────────────────────
  Reads config.yaml -> api_keys.nasa_username / nasa_password (or
  EARTHDATA_USER / EARTHDATA_PASS env vars / --user / --password), and
  automatically writes/updates a ~/.netrc entry from them -- this is the
  officially recommended way NASA's own tools expect credentials to be
  supplied for scripted access. Register free at: https://urs.earthdata.nasa.gov/
"""
from __future__ import annotations
import argparse
import asyncio
import base64
import os
import stat
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urlencode
import aiohttp
import requests
import yaml
from tqdm import tqdm


# ──────────────────────────────────────────────────────────────
#  CONFIG.YAML LOADING
# ──────────────────────────────────────────────────────────────

def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        print(f"  NOTE: {config_path} not found -- falling back to env vars / CLI args only.")
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    return cfg


# ──────────────────────────────────────────────────────────────
#  CONFIGURATION
# ──────────────────────────────────────────────────────────────

DEFAULT_START      = "2022-01-01"
DEFAULT_END        = "2024-09-30"
DEFAULT_WORKERS    = 20                # requests+threads: keep a bit more conservative
                                        # than the asyncio version was
DEFAULT_VARIABLES  = ["precipitationCal"]
MIN_VALID_SIZE_B   = 200

CMR_SEARCH_URL = (
    "https://cmr.earthdata.nasa.gov/search/granules.json"
    "?short_name=GPM_3IMERGHHL"
    "&version=07"
    "&temporal[]={start}T00:00:00Z,{end}T23:59:59Z"
    "&bounding_box=76.5,31.35,77.5,32.1"       # Mandi district bbox
    "&page_size=2000"
    "&page_num={page}"
)

OTF_BASE_URL   = "https://gpm1.gesdisc.eosdis.nasa.gov/daac-bin/OTF/HTTP_services.cgi"
OTF_FORMAT     = base64.b64encode(b"nc4/").decode()   # -> "bmM0Lw=="
OTF_SERVICE    = "L34RS_GPM"
OTF_SHORTNAME  = "GPM_3IMERGHHL"
OTF_DATASET_VERSION = "07"
OTF_API_VERSION = "1.02"


@dataclass
class Granule:
    url: str
    filename: str
    date_str: str


def build_subset_url(granule: Granule, bbox: dict, variables: list[str]) -> str:
    file_path = urlparse(granule.url).path
    bbox_str = f"{bbox['lat_min']},{bbox['lon_min']},{bbox['lat_max']},{bbox['lon_max']}"
    label = f"{granule.filename}.SUB.nc4"

    params = {
        "FILENAME": file_path,
        "BBOX": bbox_str,
        "SHORTNAME": OTF_SHORTNAME,
        "SERVICE": OTF_SERVICE,
        "DATASET_VERSION": OTF_DATASET_VERSION,
        "VERSION": OTF_API_VERSION,
        "LABEL": label,
        "FORMAT": OTF_FORMAT,
        "VARIABLES": ",".join(variables),
    }
    return f"{OTF_BASE_URL}?{urlencode(params)}"


# ──────────────────────────────────────────────────────────────
#  .netrc SETUP — the officially-supported auth path for EOSDIS
# ──────────────────────────────────────────────────────────────

def ensure_netrc(username: str, password: str) -> Path:
    """
    Writes/updates a ~/.netrc entry for urs.earthdata.nasa.gov. This is
    NASA's own recommended way of supplying credentials for scripted
    downloads -- `requests` (and curl/wget) look this up automatically
    on the login redirect, which is what actually makes the EOSDIS
    login+cookie handshake work correctly.

    Any existing entry for urs.earthdata.nasa.gov is replaced; other
    entries in the file (if any) are left untouched.
    """
    netrc_path = Path.home() / ".netrc"
    machine_line = f"machine urs.earthdata.nasa.gov login {username} password {password}"

    lines: list[str] = []
    if netrc_path.exists():
        lines = netrc_path.read_text(encoding="utf-8").splitlines()

    # Strip any existing urs.earthdata.nasa.gov block (3-4 tokens starting at "machine urs...")
    new_lines: list[str] = []
    skip_until_next_machine = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("machine urs.earthdata.nasa.gov"):
            skip_until_next_machine = True
            continue
        if skip_until_next_machine and stripped.startswith("machine "):
            skip_until_next_machine = False
        if not skip_until_next_machine:
            new_lines.append(line)

    new_lines.append(machine_line)
    netrc_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    try:
        os.chmod(netrc_path, stat.S_IRUSR | stat.S_IWUSR)   # 600 -- no-op-ish on Windows, harmless
    except Exception:
        pass

    return netrc_path


# ──────────────────────────────────────────────────────────────
#  CMR GRANULE DISCOVERY (async, no auth needed — this part already worked)
# ──────────────────────────────────────────────────────────────

async def discover_granules(start: date, end: date) -> list[Granule]:
    granules: list[Granule] = []
    page = 1
    print(f"  Discovering granules via CMR ({start} -> {end})...")

    async with aiohttp.ClientSession(
        headers={"User-Agent": "GPM-IMERG-Subset-Downloader/2.0 (research project)"}
    ) as session:
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
#  DOWNLOAD (requests + .netrc — proven to handle EOSDIS login/redirects)
# ──────────────────────────────────────────────────────────────

def make_requests_session() -> requests.Session:
    """
    A plain requests.Session with NO explicit auth set. This matters:
    requests automatically looks up ~/.netrc credentials when a redirect
    crosses to a host it doesn't have credentials for yet, which is
    exactly the EOSDIS login flow. Passing auth= explicitly (like the
    aiohttp version did) bypasses that mechanism and is what broke it.
    """
    s = requests.Session()
    s.headers.update({"User-Agent": "GPM-IMERG-Subset-Downloader/2.0 (research project)"})
    return s


def run_self_test(session: requests.Session, granule: Granule, bbox: dict, variables: list[str]) -> bool:
    url = build_subset_url(granule, bbox, variables)
    print("\n" + "=" * 60)
    print("  SELF-TEST: validating the subsetting URL + .netrc auth")
    print("=" * 60)
    print(f"  Sample granule : {granule.filename}")
    print(f"  Request URL    : {url}\n")

    try:
        resp = session.get(url, timeout=60)
        body = resp.content
        print(f"  HTTP status    : {resp.status_code}")
        print(f"  Final URL      : {resp.url}")
        print(f"  Content-Type   : {resp.headers.get('Content-Type', '')}")
        print(f"  Response size  : {len(body):,} bytes")
        if resp.history:
            print(f"  Redirect chain : {[r.status_code for r in resp.history]} -> {resp.status_code}")

        is_netcdf = body[:3] == b"CDF" or body[:4] == b"\x89HDF"
        looks_like_error = body[:20].strip().startswith((b"<", b"{", b"Error", b"error"))

        if resp.status_code == 200 and is_netcdf and not looks_like_error:
            print("\n  PASSED: response is valid NetCDF. Proceeding to full run.\n")
            return True

        print("\n  FAILED: response does not look like valid NetCDF.")
        print("  First 300 bytes of response (for diagnosis):")
        print("  " + repr(body[:300]))
        print(
            "\n  Next steps:\n"
            "    1. Confirm nasa_username/nasa_password in config.yaml are correct.\n"
            "    2. Check https://urs.earthdata.nasa.gov -> Profile -> Applications and make\n"
            "       sure 'GES DISC' (and/or 'NASA GESDISC DATA ARCHIVE') is Approved.\n"
            "    3. Try opening the printed Request URL directly in a browser while logged\n"
            "       into Earthdata -- if it downloads fine there, the URL pattern is right\n"
            "       and it's purely an account-authorization issue, not a script bug.\n"
            "  Falling back to nasa_collector_fast.py (full global files, no subsetting)\n"
            "  is always a safe option if you'd rather not debug this further.\n"
        )
        return False

    except Exception as exc:
        print(f"\n  FAILED: request raised an exception: {exc}\n")
        return False


def download_one(
    session: requests.Session,
    granule: Granule,
    output_dir: Path,
    bbox: dict,
    variables: list[str],
    stats: dict,
    stats_lock,
    max_retries: int = 5,
    backoff_factor: float = 2.0,
    retry_on_status: tuple[int, ...] = (429, 500, 502, 503, 504),
    timeout_seconds: int = 60,
) -> None:
    if granule.date_str != "unknown":
        year, month = granule.date_str[:4], granule.date_str[5:7]
        dest_dir = output_dir / year / month / granule.date_str
    else:
        dest_dir = output_dir / "unknown"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"{granule.filename}.SUB.nc4"

    def bump(key: str, n: int = 1) -> None:
        with stats_lock:
            stats[key] = stats.get(key, 0) + n

    if dest_path.exists() and dest_path.stat().st_size > MIN_VALID_SIZE_B:
        bump("skipped")
        return

    url = build_subset_url(granule, bbox, variables)

    for attempt in range(max_retries + 1):
        try:
            resp = session.get(url, timeout=timeout_seconds)
            if resp.status_code == 200:
                body = resp.content
                is_netcdf = body[:3] == b"CDF" or body[:4] == b"\x89HDF"
                if not is_netcdf or len(body) < MIN_VALID_SIZE_B:
                    bump("bad_response")
                    bump("failed")
                    return
                dest_path.write_bytes(body)
                bump("downloaded")
                bump("bytes", len(body))
                return
            elif resp.status_code == 401:
                bump("auth_errors")
                bump("failed")
                return
            elif resp.status_code in retry_on_status and attempt < max_retries:
                bump("retries")
                time.sleep(backoff_factor ** attempt)
                continue
            else:
                bump("failed")
                return
        except requests.exceptions.Timeout:
            if attempt < max_retries:
                bump("retries")
                time.sleep(backoff_factor ** attempt)
                continue
            bump("failed")
            return
        except Exception:
            bump("failed")
            return


# ──────────────────────────────────────────────────────────────
#  MAIN
# ──────────────────────────────────────────────────────────────

def run(
    start: date,
    end: date,
    output_dir: Path,
    bbox: dict,
    variables: list[str],
    max_workers: int,
    test_only: bool,
    max_retries: int = 5,
    backoff_factor: float = 2.0,
    retry_on_status: tuple[int, ...] = (429, 500, 502, 503, 504),
    timeout_seconds: int = 60,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    granules = asyncio.run(discover_granules(start, end))
    if not granules:
        print("  No granules found. Check date range, bbox, and CMR availability.")
        return

    session = make_requests_session()

    passed = run_self_test(session, granules[0], bbox, variables)
    if not passed:
        print("  Aborting bulk run because the self-test failed. See instructions above.")
        return
    if test_only:
        print("  --test-only was set. Stopping here.")
        return

    already_done = sum(
        1 for g in granules
        if (output_dir / g.date_str[:4] / g.date_str[5:7] / g.date_str
            / f"{g.filename}.SUB.nc4").exists()
        and (output_dir / g.date_str[:4] / g.date_str[5:7] / g.date_str
             / f"{g.filename}.SUB.nc4").stat().st_size > MIN_VALID_SIZE_B
    )
    to_download = len(granules) - already_done
    print(f"  {len(granules):,} total granules | {already_done:,} already on disk | "
          f"{to_download:,} to download")
    print(f"  Concurrency : {max_workers} threads")
    print(f"  Variables   : {variables}")
    print(f"  Bbox        : {bbox}")
    print(f"  Output dir  : {output_dir.resolve()}\n")

    if to_download == 0:
        print("  All files already downloaded. Nothing to do.")
        return

    stats: dict = {}
    import threading
    stats_lock = threading.Lock()

    # Each thread gets its OWN requests.Session (Session objects aren't
    # guaranteed thread-safe for concurrent use across threads, same
    # reasoning as the "fresh client per thread" pattern in era5_collector.py)
    thread_local = threading.local()

    def get_thread_session() -> requests.Session:
        if not hasattr(thread_local, "session"):
            thread_local.session = make_requests_session()
        return thread_local.session

    def worker(g: Granule) -> None:
        s = get_thread_session()
        download_one(
            s, g, output_dir, bbox, variables, stats, stats_lock,
            max_retries=max_retries, backoff_factor=backoff_factor,
            retry_on_status=retry_on_status, timeout_seconds=timeout_seconds,
        )

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(worker, g) for g in granules]
        for _ in tqdm(as_completed(futures), total=len(futures), desc="Downloading subsets", unit="file"):
            pass
    elapsed = time.perf_counter() - t0

    total_mb = stats.get("bytes", 0) / (1024 ** 2)
    print(f"\n{'='*60}")
    print(f"  DOWNLOAD COMPLETE")
    print(f"{'='*60}")
    print(f"  Downloaded    : {stats.get('downloaded', 0):,} files  ({total_mb:.1f} MB total)")
    print(f"  Skipped       : {stats.get('skipped', 0):,} (already on disk)")
    print(f"  Retried       : {stats.get('retries', 0):,}")
    print(f"  Failed        : {stats.get('failed', 0):,}  (bad_response: {stats.get('bad_response', 0):,})")
    print(f"  Time          : {elapsed/60:.1f} min")
    print(f"  Output        : {output_dir.resolve()}")

    if stats.get("failed", 0) > 0:
        print(f"\n  {stats['failed']} files failed. Re-run the script to retry them —")
        print(f"  completed files are skipped automatically (resume support).")
    if stats.get("auth_errors", 0) > 0:
        print(f"\n  {stats['auth_errors']} files failed with 401 (auth error). Check credentials/.netrc.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bbox-subset NASA GPM IMERG downloader (requests + .netrc)")
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--config", default=None)
    parser.add_argument("--user", default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--variables", default=None)
    parser.add_argument("--test-only", action="store_true")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    config_path = Path(args.config) if args.config else script_dir.parent / "config" / "config.yaml"
    cfg = load_config(config_path)
    cfg_nasa = cfg.get("sources", {}).get("nasa_gpm", {})
    cfg_api_keys = cfg.get("api_keys", {})
    cfg_http = cfg.get("http", {})
    cfg_loc = cfg.get("location", {}).get("bounding_box", {})

    if args.output:
        output_dir = Path(args.output)
    elif cfg_nasa.get("download_dir"):
        output_dir = (script_dir.parent / cfg_nasa["download_dir"] / "raw_subset")
    else:
        output_dir = script_dir.parent / "datasets" / "source_2_nasa_gpm" / "raw_subset"

    earthdata_user = args.user or os.environ.get("EARTHDATA_USER") or cfg_api_keys.get("nasa_username")
    earthdata_pass = args.password or os.environ.get("EARTHDATA_PASS") or cfg_api_keys.get("nasa_password")
    placeholder_markers = ("ENTER_YOUR_", "YOUR_NASA")
    if earthdata_user and any(m in earthdata_user for m in placeholder_markers):
        earthdata_user = None
    if earthdata_pass and any(m in earthdata_pass for m in placeholder_markers):
        earthdata_pass = None

    if not earthdata_user or not earthdata_pass:
        print(
            "\n  NASA EARTHDATA CREDENTIALS REQUIRED\n"
            "  Set nasa_username / nasa_password in config.yaml under api_keys,\n"
            "  or pass --user / --password, or set EARTHDATA_USER / EARTHDATA_PASS.\n"
            "  Register free at: https://urs.earthdata.nasa.gov/\n"
        )
        sys.exit(1)

    netrc_path = ensure_netrc(earthdata_user, earthdata_pass)
    print(f"  Credentials written to: {netrc_path}")

    start_str = args.start or cfg_nasa.get("start_date") or DEFAULT_START
    end_str = args.end or cfg_nasa.get("end_date") or DEFAULT_END
    start = date.fromisoformat(start_str)
    end = date.fromisoformat(end_str)

    days_requested = (end - start).days + 1
    if days_requested > 365 * 3 + 10:
        print(
            f"  NOTE: you're requesting {days_requested:,} days. This script defaults to\n"
            f"  {DEFAULT_START} -> {DEFAULT_END} (GPM's realistic project window).\n"
            f"  If this wide range isn't intentional, pass --start/--end explicitly.\n"
        )

    bbox = {
        "lat_min": cfg_loc.get("lat_min", 31.35),
        "lat_max": cfg_loc.get("lat_max", 32.1),
        "lon_min": cfg_loc.get("lon_min", 76.5),
        "lon_max": cfg_loc.get("lon_max", 77.5),
    }

    variables = (
        [v.strip() for v in args.variables.split(",")] if args.variables
        else cfg_nasa.get("variables", DEFAULT_VARIABLES)
    )

    print("=" * 60)
    print("  NASA GPM IMERG SUBSET DOWNLOADER (requests + .netrc)")
    print("=" * 60)
    print(f"  Config     : {config_path}  {'(found)' if config_path.exists() else '(not found -- using defaults)'}")
    print(f"  Date range : {start} -> {end}  ({days_requested:,} days)")
    print(f"  Bbox       : {bbox}")
    print(f"  Variables  : {variables}")
    print(f"  Workers    : {args.workers} concurrent threads")
    print(f"  Output     : {output_dir.resolve()}")
    print()

    run(
        start=start, end=end, output_dir=output_dir, bbox=bbox, variables=variables,
        max_workers=args.workers, test_only=args.test_only,
        max_retries=cfg_http.get("max_retries", 5),
        backoff_factor=cfg_http.get("backoff_factor", 2.0),
        retry_on_status=tuple(cfg_http.get("retry_on_status", [429, 500, 502, 503, 504])),
        timeout_seconds=cfg_http.get("timeout_seconds", 60),
    )


if __name__ == "__main__":
    main()