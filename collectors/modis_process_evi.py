"""
modis_process_evi.py
==============================================================================
Turns raw MOD13Q1 EVI/VI_Quality GeoTIFFs into a tidy district-level EVI
time series, ready to fold into merger.py the same way ERA5-Land and
climate indices are (16-day -> forward-filled hourly).

WHY THIS IS NEEDED
------------------
digital_twin/vegetation/MODIS/cleaned/ currently contains only raw rasters:
    MOD13Q1.061__250m_16_days_EVI_doy<YYYYDDD>000000_aid0001.tif
    MOD13Q1.061__250m_16_days_VI_Quality_doy<YYYYDDD>000000_aid0001.tif
There is no tabular time series yet -- this script produces one.

WHAT IT DOES (per date)
------------------------
  1. Parse the acquisition date from the filename's doyYYYYDDD code.
  2. Open the EVI raster, clip to the Mandi district boundary (GeoJSON).
  3. Open the matching VI_Quality raster, extract the MODLAND QA bits
     (bits 0-1 of the 16-bit quality word) and keep only pixels flagged
     "good" (00) or "marginal" (01) -- standard MOD13 QA practice.
  4. Apply the MOD13Q1 EVI scale factor (0.0001) to convert raw DN to
     the actual EVI value (~ -0.2 to 1.0 range).
  5. Average the QA-masked, scaled EVI pixels within the district
     boundary -> one EVI value per date.
  6. Also record the good-pixel fraction (data-quality diagnostic).

OUTPUT
------
  digital_twin/vegetation/MODIS/cleaned/mandi_evi_timeseries.csv
  columns: date, evi_mean, good_pixel_pct, n_pixels_total

This file is what merger.py's (future) load_modis_evi() would read --
16-day cadence, forward-filled to hourly, same pattern as ERA5-Land.

Requirements
------------
  pip install rasterio geopandas shapely numpy pandas --break-system-packages

Usage
-----
  python modis_process_evi.py
  python modis_process_evi.py --district mandi
  python modis_process_evi.py --tif-dir path/to/cleaned --boundary path/to/mandi_district.geojson
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import rasterio
    from rasterio.mask import mask as rio_mask
    import geopandas as gpd
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Run: pip install rasterio geopandas shapely numpy pandas --break-system-packages")
    sys.exit(1)


# MOD13Q1 EVI band: raw DN -> actual EVI. Valid range -2000..10000 (raw).
EVI_SCALE_FACTOR = 0.0001
EVI_FILL_VALUE = -3000          # MOD13Q1 _FillValue for EVI
EVI_VALID_MIN, EVI_VALID_MAX = -2000, 10000

# QA: MODLAND VI usefulness lives in bits 0-1 of the 16-bit quality word.
# 00 = good data, 01 = marginal data -- both kept. 10/11 = unreliable/cloud.
QA_GOOD_MASK = 0b11
QA_GOOD_VALUES = {0b00, 0b01}

DOY_RE = re.compile(r"doy(\d{4})(\d{3})\d{6}")


def parse_date_from_filename(path: Path) -> datetime | None:
    """Extract the acquisition date from a MOD13Q1 AppEEARS filename."""
    m = DOY_RE.search(path.name)
    if not m:
        return None
    year, doy = int(m.group(1)), int(m.group(2))
    return datetime(year, 1, 1) + timedelta(days=doy - 1)


def find_quality_pair(evi_path: Path) -> Path | None:
    """Given an EVI tif path, find its matching VI_Quality tif."""
    qa_name = evi_path.name.replace("_EVI_", "_VI_Quality_")
    qa_path = evi_path.parent / qa_name
    return qa_path if qa_path.exists() else None


def process_one_date(
    evi_path: Path, qa_path: Path | None, boundary_geom
) -> dict | None:
    """Clip, QA-mask, scale, and average one date's EVI raster."""
    date = parse_date_from_filename(evi_path)
    if date is None:
        return None

    try:
        with rasterio.open(evi_path) as src:
            evi_clip, _ = rio_mask(src, [boundary_geom], crop=True, filled=True, nodata=EVI_FILL_VALUE)
            evi = evi_clip[0].astype(float)
    except Exception as exc:
        print(f"  WARNING: could not read {evi_path.name}: {exc}")
        return None

    valid = (evi != EVI_FILL_VALUE) & (evi >= EVI_VALID_MIN) & (evi <= EVI_VALID_MAX)
    n_total = int(valid.sum())

    if qa_path is not None:
        try:
            with rasterio.open(qa_path) as qsrc:
                qa_clip, _ = rio_mask(qsrc, [boundary_geom], crop=True, filled=True, nodata=0)
                qa = qa_clip[0].astype(int)
            qa_bits = qa & QA_GOOD_MASK
            good_mask = valid & np.isin(qa_bits, list(QA_GOOD_VALUES))
        except Exception as exc:
            print(f"  WARNING: could not read QA {qa_path.name}: {exc}. Using all valid pixels.")
            good_mask = valid
    else:
        good_mask = valid

    n_good = int(good_mask.sum())
    if n_good == 0:
        return {
            "date": date, "evi_mean": np.nan,
            "good_pixel_pct": 0.0, "n_pixels_total": n_total,
        }

    evi_scaled = evi[good_mask] * EVI_SCALE_FACTOR
    return {
        "date": date,
        "evi_mean": float(evi_scaled.mean()),
        "good_pixel_pct": round(n_good / n_total * 100, 1) if n_total else 0.0,
        "n_pixels_total": n_total,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Process MOD13Q1 EVI rasters into a tidy time series.")
    parser.add_argument("--district", default="mandi")
    parser.add_argument(
        "--tif-dir", default=None,
        help="Directory containing the EVI/VI_Quality tifs (default: digital_twin/vegetation/MODIS/cleaned)",
    )
    parser.add_argument(
        "--boundary", default=None,
        help="Path to district GeoJSON (default: digital_twin/metadata/boundaries/<district>_district.geojson)",
    )
    args = parser.parse_args()

    tif_dir = Path(args.tif_dir) if args.tif_dir else Path("digital_twin/vegetation/MODIS/cleaned")
    boundary_path = (
        Path(args.boundary) if args.boundary
        else Path(f"digital_twin/metadata/boundaries/{args.district}_district.geojson")
    )

    if not tif_dir.exists():
        print(f"ERROR: tif directory not found: {tif_dir}")
        sys.exit(1)
    if not boundary_path.exists():
        print(f"ERROR: boundary GeoJSON not found: {boundary_path}")
        sys.exit(1)

    gdf = gpd.read_file(boundary_path)
    boundary_geom = gdf.union_all() if hasattr(gdf, "union_all") else gdf.unary_union

    evi_paths = sorted(tif_dir.glob("MOD13Q1*_EVI_doy*.tif"))
    if not evi_paths:
        print(f"ERROR: no EVI tifs found in {tif_dir} matching 'MOD13Q1*_EVI_doy*.tif'")
        sys.exit(1)

    print(f"Found {len(evi_paths)} EVI raster(s) in {tif_dir}")
    print(f"District boundary: {boundary_path}")

    records = []
    for i, evi_path in enumerate(evi_paths, 1):
        qa_path = find_quality_pair(evi_path)
        rec = process_one_date(evi_path, qa_path, boundary_geom)
        if rec is not None:
            records.append(rec)
        if i % 50 == 0 or i == len(evi_paths):
            print(f"  Processed {i}/{len(evi_paths)}...")

    if not records:
        print("ERROR: no dates processed successfully.")
        sys.exit(1)

    df = pd.DataFrame(records).sort_values("date").reset_index(drop=True)
    n_nan = df["evi_mean"].isna().sum()
    if n_nan:
        print(f"  NOTE: {n_nan} date(s) had zero good-quality pixels (EVI left as NaN).")

    out_dir = tif_dir  # keep output alongside the source rasters
    out_path = out_dir / f"{args.district}_evi_timeseries.csv"
    df.to_csv(out_path, index=False)

    print(f"\nSaved: {out_path}")
    print(f"Rows: {len(df):,}  Date range: {df['date'].min()} -> {df['date'].max()}")
    print(f"Mean EVI: {df['evi_mean'].mean():.4f}  Mean good-pixel %: {df['good_pixel_pct'].mean():.1f}%")


if __name__ == "__main__":
    main()
