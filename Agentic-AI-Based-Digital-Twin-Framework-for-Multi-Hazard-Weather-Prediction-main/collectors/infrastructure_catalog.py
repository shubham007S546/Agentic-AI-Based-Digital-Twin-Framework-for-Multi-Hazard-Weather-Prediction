"""
infrastructure_catalog.py
==============================================================================
Summarizes digital_twin/infrastructure/cleaned/*.geojson into a small
per-district feature table -- one row per district, one column per
category (hospital count, total road length_km, etc.).

WHY THIS IS SEPARATE FROM merger.py
------------------------------------
Infrastructure is static (a hospital doesn't have an hourly rainfall-style
value) -- it doesn't belong in the hourly time-series merge. Instead this
produces a tiny reference table you LEFT-JOIN onto your ML-ready dataset
on the 'district' column, so every hourly row for Mandi gets the same
constant infra_* columns.

INPUT (confirmed format, not guessed)
--------------------------------------
  digital_twin/infrastructure/cleaned/<district>_<Category>_cleaned.geojson
  e.g. mandi_Hospitals_cleaned.geojson, kullu_Roads_cleaned.geojson

For each file:
  - Point/MultiPoint layers  (Hospitals, Schools, Colleges, Police_Stations,
    Fire_Stations, Government_Offices, Bus_Stops, Railway_Stations,
    Airports_Helipads, Power_Substations, Hydropower_Stations, Dams,
    Villages, Towns) -> feature COUNT.
  - LineString/MultiLineString layers (Roads, Transmission_Lines)
    -> total length in km (reprojected to a metric CRS for HP: EPSG:32643).

OUTPUT
------
  digital_twin/infrastructure/infra_catalog.csv
  One row per district. Columns like:
    district, hospitals_count, schools_count, roads_length_km, ...

Requirements
------------
  pip install geopandas shapely --break-system-packages

Usage
-----
  python infrastructure_catalog.py
  python infrastructure_catalog.py --cleaned-dir path/to/cleaned
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

try:
    import geopandas as gpd
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Run: pip install geopandas shapely --break-system-packages")
    sys.exit(1)


# Metric CRS for Himachal Pradesh (UTM zone 43N) -- used only for length calcs.
METRIC_CRS = "EPSG:32643"

FILENAME_RE = re.compile(r"^([a-z]+)_(.+)_cleaned\.geojson$", re.IGNORECASE)


def summarize_layer(path: Path) -> tuple[str, str, dict]:
    """
    Read one <district>_<Category>_cleaned.geojson and return
    (district, category, {metric_name: value}).
    """
    m = FILENAME_RE.match(path.name)
    if not m:
        raise ValueError(f"Filename doesn't match <district>_<Category>_cleaned.geojson: {path.name}")
    district, category = m.group(1).lower(), m.group(2)

    gdf = gpd.read_file(path)
    if gdf.empty:
        return district, category, {f"{category.lower()}_count": 0}

    geom_types = set(gdf.geometry.geom_type.unique())
    metrics: dict = {}

    if geom_types & {"LineString", "MultiLineString"}:
        # Length-based layer (roads, transmission lines)
        gdf_metric = gdf.to_crs(METRIC_CRS) if gdf.crs else gdf.set_crs("EPSG:4326").to_crs(METRIC_CRS)
        total_km = gdf_metric.geometry.length.sum() / 1000.0
        metrics[f"{category.lower()}_length_km"] = round(total_km, 2)
        metrics[f"{category.lower()}_count"] = len(gdf)
    elif geom_types & {"Polygon", "MultiPolygon"}:
        gdf_metric = gdf.to_crs(METRIC_CRS) if gdf.crs else gdf.set_crs("EPSG:4326").to_crs(METRIC_CRS)
        total_km2 = gdf_metric.geometry.area.sum() / 1_000_000.0
        metrics[f"{category.lower()}_area_km2"] = round(total_km2, 2)
        metrics[f"{category.lower()}_count"] = len(gdf)
    else:
        # Point / MultiPoint -> just count
        metrics[f"{category.lower()}_count"] = len(gdf)

    return district, category, metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize infrastructure GeoJSON layers per district.")
    parser.add_argument(
        "--cleaned-dir", default="digital_twin/infrastructure/cleaned",
        help="Directory containing <district>_<Category>_cleaned.geojson files",
    )
    parser.add_argument(
        "--out", default="digital_twin/infrastructure/infra_catalog.csv",
    )
    args = parser.parse_args()

    cleaned_dir = Path(args.cleaned_dir)
    if not cleaned_dir.exists():
        print(f"ERROR: directory not found: {cleaned_dir}")
        sys.exit(1)

    geojsons = sorted(cleaned_dir.glob("*_cleaned.geojson"))
    if not geojsons:
        print(f"ERROR: no *_cleaned.geojson files found in {cleaned_dir}")
        sys.exit(1)

    print(f"Found {len(geojsons)} infrastructure layer(s) in {cleaned_dir}")

    per_district: dict[str, dict] = defaultdict(dict)
    failed = []

    for path in geojsons:
        try:
            district, category, metrics = summarize_layer(path)
            per_district[district].update(metrics)
            print(f"  {district:<8} {category:<25} -> {metrics}")
        except Exception as exc:
            failed.append((path.name, str(exc)))
            print(f"  WARNING: failed on {path.name}: {exc}")

    if not per_district:
        print("ERROR: no layers processed successfully.")
        sys.exit(1)

    df = pd.DataFrame.from_dict(per_district, orient="index")
    df.index.name = "district"
    df = df.fillna(0).reset_index().sort_values("district")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)

    print(f"\nSaved: {out_path}")
    print(f"Districts: {list(df['district'])}")
    print(f"Columns  : {list(df.columns)}")
    if failed:
        print(f"\n{len(failed)} layer(s) failed to process:")
        for name, err in failed:
            print(f"  {name}: {err}")


if __name__ == "__main__":
    main()
