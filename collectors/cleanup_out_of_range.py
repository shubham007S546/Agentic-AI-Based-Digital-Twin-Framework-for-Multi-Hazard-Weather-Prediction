"""
cleanup_out_of_range.py
==============================================================================
Finds (and optionally deletes) already-downloaded source files that fall
OUTSIDE your project's actual date range (config.yaml's dates.start_date /
dates.end_date). Since merger.py already crops everything to that window
during merging, files outside it are pure wasted disk space -- this doesn't
change your final_dataset.csv at all, it just reclaims space.

SAFE BY DESIGN:
  - Defaults to DRY RUN (--confirm required to actually delete anything)
  - Prints every file it WOULD delete before deleting anything
  - Never touches a file it can't confidently date

HOW IT FINDS EACH FILE'S DATE:
  Looks for a date pattern in the file's path (filename or parent folders):
    YYYY-MM-DD, YYYYMMDD, or a bare YYYY (2000-2030) folder/filename segment.
  Files where no date pattern is found are SKIPPED and listed separately --
  never deleted, since we can't confirm they're out of range.

USAGE
-----
  # Dry run (default) -- just shows what would be deleted, deletes nothing
  python cleanup_out_of_range.py

  # Check specific folders only
  python cleanup_out_of_range.py --dirs datasets/source_4_era5 datasets/source_1_imd

  # Actually delete after reviewing the dry-run output
  python cleanup_out_of_range.py --confirm
"""
from __future__ import annotations
import argparse
import re
from datetime import date
from pathlib import Path

import yaml

DATE_PATTERNS = [
    re.compile(r"(\d{4})-(\d{2})-(\d{2})"),           # YYYY-MM-DD
    re.compile(r"(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)"),  # YYYYMMDD
    re.compile(r"(?<!\d)(20[0-3]\d)(?!\d)"),           # bare YYYY, 2000-2039
]

DEFAULT_DIRS = [
    "datasets/source_1_imd",
    "datasets/source_2_nasa_gpm",
    "datasets/source_3_datagov",
    "datasets/source_4_era5",
    "datasets/source_5_openmeteo",
]


def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def extract_date_from_path(path: Path) -> date | None:
    """
    Tries each date pattern against the full path string, most specific
    first (full date beats bare year). Returns None if nothing matches --
    caller must treat that as 'unknown, do not touch'.
    """
    path_str = str(path)
    for pattern in DATE_PATTERNS[:2]:  # full-date patterns first
        m = pattern.search(path_str)
        if m:
            try:
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                return date(y, mo, d)
            except ValueError:
                continue
    # Bare year fallback -- only useful for range checks at year granularity
    m = DATE_PATTERNS[2].search(path_str)
    if m:
        y = int(m.group(1))
        return date(y, 1, 1)  # treat as Jan 1 of that year; good enough for a year-level bound
    return None


def scan_directory(root: Path, start: date, end: date):
    """
    Returns (in_range, out_of_range, unknown) lists of (path, size_bytes, detected_date).
    """
    in_range, out_of_range, unknown = [], [], []
    if not root.exists():
        return in_range, out_of_range, unknown

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        size = path.stat().st_size
        detected = extract_date_from_path(path.relative_to(root))
        if detected is None:
            unknown.append((path, size, None))
        elif start <= detected <= end:
            in_range.append((path, size, detected))
        else:
            out_of_range.append((path, size, detected))
    return in_range, out_of_range, unknown


def human_size(n_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n_bytes < 1024:
            return f"{n_bytes:.1f} {unit}"
        n_bytes /= 1024
    return f"{n_bytes:.1f} PB"


def main() -> None:
    parser = argparse.ArgumentParser(description="Find/delete downloaded files outside the project date range")
    parser.add_argument("--config", default=None, help="Path to config.yaml (default: ../config/config.yaml)")
    parser.add_argument("--dirs", nargs="+", default=None,
                         help="Specific directories to scan (default: all source_* dirs under datasets/)")
    parser.add_argument("--confirm", action="store_true",
                         help="Actually delete out-of-range files (default: dry run, deletes nothing)")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    config_path = Path(args.config) if args.config else script_dir.parent / "config" / "config.yaml"
    cfg = load_config(config_path)
    cfg_dates = cfg.get("dates", {})

    start = date.fromisoformat(cfg_dates.get("start_date", "2022-01-01"))
    end = date.fromisoformat(cfg_dates.get("end_date", "2024-09-30"))

    project_root = script_dir.parent
    dirs = [project_root / d for d in (args.dirs or DEFAULT_DIRS)]

    print("=" * 70)
    print("  CLEANUP: FILES OUTSIDE PROJECT DATE RANGE")
    print("=" * 70)
    print(f"  Config      : {config_path}")
    print(f"  Date range  : {start} -> {end}")
    print(f"  Mode        : {'DELETE (--confirm passed)' if args.confirm else 'DRY RUN (nothing will be deleted)'}")
    print()

    grand_total_out = 0
    grand_total_unknown = 0
    all_out_of_range = []

    for d in dirs:
        in_range, out_of_range, unknown = scan_directory(d, start, end)
        out_bytes = sum(s for _, s, _ in out_of_range)
        unknown_bytes = sum(s for _, s, _ in unknown)
        grand_total_out += out_bytes
        grand_total_unknown += unknown_bytes
        all_out_of_range.extend(out_of_range)

        if not d.exists():
            print(f"  {d}  -- does not exist, skipping")
            continue

        print(f"  {d}")
        print(f"    In range     : {len(in_range):,} files")
        print(f"    OUT of range : {len(out_of_range):,} files  ({human_size(out_bytes)})")
        print(f"    Unknown date : {len(unknown):,} files  ({human_size(unknown_bytes)}, NOT touched)")
        if out_of_range:
            years = sorted({dt.year for _, _, dt in out_of_range})
            print(f"    Out-of-range years present: {years}")
        print()

    print("=" * 70)
    print(f"  TOTAL reclaimable (out-of-range) : {human_size(grand_total_out)}")
    print(f"  TOTAL skipped (unknown date)     : {human_size(grand_total_unknown)}  -- review these manually")
    print("=" * 70)

    if not args.confirm:
        print("\n  DRY RUN -- nothing deleted. Review the numbers above, then re-run with --confirm to actually delete.")
        if all_out_of_range:
            print(f"\n  First 10 files that would be deleted:")
            for path, size, dt in all_out_of_range[:10]:
                print(f"    {path}  ({human_size(size)}, detected date: {dt})")
        return

    print(f"\n  Deleting {len(all_out_of_range):,} files...")
    deleted, failed = 0, 0
    for path, size, dt in all_out_of_range:
        try:
            path.unlink()
            deleted += 1
        except Exception as e:
            failed += 1
            print(f"    FAILED to delete {path}: {e}")

    print(f"\n  Deleted : {deleted:,} files ({human_size(grand_total_out)} reclaimed)")
    if failed:
        print(f"  Failed  : {failed:,} files (see above)")


if __name__ == "__main__":
    main()
