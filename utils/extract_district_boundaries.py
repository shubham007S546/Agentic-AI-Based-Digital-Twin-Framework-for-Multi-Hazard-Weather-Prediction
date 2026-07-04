"""
extract_district_boundary.py
-----------------------------
Utility to extract individual district boundaries from the national
geoBoundaries ADM2 GeoJSON file for the Mandi digital-twin project.

Reads:
    metadata/boundaries/geoBoundaries-IND-ADM2.geojson

Writes (one file per requested district, matched on the `shapeName` column):
    metadata/boundaries/mandi_district.geojson
    metadata/boundaries/kullu_district.geojson
    metadata/boundaries/chamba_district.geojson

Usage:
    python utils/extract_district_boundary.py

    # Optional overrides
    python utils/extract_district_boundary.py \
        --source metadata/boundaries/geoBoundaries-IND-ADM2.geojson \
        --outdir metadata/boundaries \
        --districts Mandi Kullu Chamba
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Iterable

try:
    import geopandas as gpd
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "geopandas is required for this script. Install it with:\n"
        "    pip install geopandas"
    ) from exc


# --------------------------------------------------------------------------- #
# Logging setup
# --------------------------------------------------------------------------- #
logger = logging.getLogger("extract_district_boundary")


def configure_logging(verbose: bool = False) -> None:
    """Configure a simple, readable console logger."""
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", "%H:%M:%S")
    )
    logger.setLevel(level)
    logger.handlers.clear()
    logger.addHandler(handler)


# --------------------------------------------------------------------------- #
# Core logic
# --------------------------------------------------------------------------- #
# Resolve paths relative to the project root (parent of this script's `utils/`
# folder), not the current working directory. This makes the script work the
# same whether it's launched from the project root, from utils/, or via an
# IDE "Run" button, as long as the file layout below matches your project:
#
#   <project_root>/
#     utils/extract_district_boundary.py   <- this file
#     digital_twin/metadata/boundaries/geoBoundaries-IND-ADM2.geojson
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = PROJECT_ROOT / "digital_twin" / "metadata" / "boundaries" / "geoBoundaries-IND-ADM2.geojson"
DEFAULT_OUTDIR = PROJECT_ROOT / "digital_twin" / "metadata" / "boundaries"
DEFAULT_DISTRICTS = ("Mandi", "Kullu", "Chamba")
SHAPE_NAME_COLUMN = "shapeName"


def load_boundaries(source_path: Path) -> "gpd.GeoDataFrame":
    """
    Load the national ADM2 boundary GeoJSON.

    Raises:
        FileNotFoundError: if the source file does not exist.
        ValueError: if the file cannot be parsed or lacks the expected column.
    """
    if not source_path.exists():
        raise FileNotFoundError(f"Source boundary file not found: {source_path}")

    logger.info("Loading national boundary file: %s", source_path)
    try:
        gdf = gpd.read_file(source_path)
    except Exception as exc:
        raise ValueError(f"Failed to read GeoJSON at {source_path}: {exc}") from exc

    if SHAPE_NAME_COLUMN not in gdf.columns:
        raise ValueError(
            f"Expected column '{SHAPE_NAME_COLUMN}' not found in {source_path}. "
            f"Available columns: {list(gdf.columns)}"
        )

    logger.info("Loaded %d features with columns: %s", len(gdf), list(gdf.columns))
    return gdf


def extract_district(gdf: "gpd.GeoDataFrame", district_name: str) -> "gpd.GeoDataFrame":
    """
    Extract rows matching a district name (case-insensitive, whitespace-tolerant)
    against the shapeName column.

    Raises:
        ValueError: if no matching district is found.
    """
    normalized_target = district_name.strip().lower()
    mask = gdf[SHAPE_NAME_COLUMN].astype(str).str.strip().str.lower() == normalized_target
    matches = gdf[mask]

    if matches.empty:
        raise ValueError(
            f"No district matching '{district_name}' found in '{SHAPE_NAME_COLUMN}' column."
        )

    if len(matches) > 1:
        logger.warning(
            "Multiple (%d) features matched '%s'; keeping all of them in output.",
            len(matches),
            district_name,
        )

    return matches


def save_district(gdf: "gpd.GeoDataFrame", output_path: Path) -> None:
    """Save a district GeoDataFrame to a GeoJSON file, creating dirs as needed."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        gdf.to_file(output_path, driver="GeoJSON")
    except Exception as exc:
        raise IOError(f"Failed to write {output_path}: {exc}") from exc
    logger.info("Saved -> %s (%d feature(s))", output_path, len(gdf))


def build_output_filename(district_name: str) -> str:
    """Standardize output filenames, e.g. 'Mandi' -> 'mandi_district.geojson'."""
    return f"{district_name.strip().lower()}_district.geojson"


def extract_districts(
    source_path: Path,
    output_dir: Path,
    districts: Iterable[str],
) -> dict[str, Path]:
    """
    Full pipeline: load source, extract each requested district, save each output.

    Returns:
        Mapping of district name -> output file path for successfully saved districts.
    """
    gdf = load_boundaries(source_path)
    results: dict[str, Path] = {}
    failures: list[str] = []

    for district in districts:
        logger.info("Processing district: %s", district)
        try:
            district_gdf = extract_district(gdf, district)
            out_path = output_dir / build_output_filename(district)
            save_district(district_gdf, out_path)
            results[district] = out_path
        except ValueError as exc:
            logger.error("Skipping '%s': %s", district, exc)
            failures.append(district)
        except IOError as exc:
            logger.error("Could not save '%s': %s", district, exc)
            failures.append(district)

    logger.info(
        "Done. %d/%d district(s) extracted successfully.",
        len(results),
        len(results) + len(failures),
    )
    if failures:
        logger.warning("Failed districts: %s", ", ".join(failures))

    return results


# --------------------------------------------------------------------------- #
# CLI entry point
# --------------------------------------------------------------------------- #
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract individual district boundaries from a national ADM2 GeoJSON."
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help=f"Path to source GeoJSON (default: {DEFAULT_SOURCE}). "
             f"Resolved relative to this script's location, not the CWD.",
    )
    parser.add_argument(
        "--outdir",
        type=Path,
        default=DEFAULT_OUTDIR,
        help=f"Output directory for extracted district files (default: {DEFAULT_OUTDIR})",
    )
    parser.add_argument(
        "--districts",
        nargs="+",
        default=list(DEFAULT_DISTRICTS),
        help=f"District names to extract (default: {' '.join(DEFAULT_DISTRICTS)})",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose (debug) logging.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(verbose=args.verbose)

    logger.info("Starting district boundary extraction")
    logger.info("Source     : %s", args.source)
    logger.info("Output dir : %s", args.outdir)
    logger.info("Districts  : %s", ", ".join(args.districts))

    try:
        results = extract_districts(args.source, args.outdir, args.districts)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("Fatal error: %s", exc)
        return 1

    if not results:
        logger.error("No districts were extracted successfully.")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())