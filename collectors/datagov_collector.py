"""
collectors/datagov_collector.py
══════════════════════════════════════════════════════════════════════════════
SOURCE 2 — data.gov.in OGD Platform
         Daily District-wise Rainfall — NRSC VIC MODEL
         Ministry of Jal Shakti / National Water Informatics Centre (NWIC)

Resource ID : 6c05cd1b-ed59-40c2-bc31-e314f39c6971
Portal      : https://data.gov.in
API base    : https://api.data.gov.in/resource/{resource_id}

What this dataset contains
──────────────────────────
  Daily rainfall observations at district/sub-basin level across India,
  sourced from the NRSC VIC (Variable Infiltration Capacity) hydrological
  model. Covers flood forecasting and water resource monitoring use cases.
  Published by the Department of Water Resources, River Development &
  Ganga Rejuvenation, Ministry of Jal Shakti.

What this collector does
────────────────────────
  1.  Reads all settings from config/config.yaml. No hard-coded values.
  2.  Loops year by year from start_date.year → end_date.year.
  3.  For each year, paginates through ALL records with:
        filters[Year]         = YYYY
        filters[State]        = Himachal Pradesh
        filters[Agency_name]  = NRSC VIC MODEL
      (District filter attempted first; Python-level fallback if rejected)
  4.  Saves each year's raw API response as a JSON file.
  5.  After all years downloaded, applies basic cleaning ONLY:
        • concatenate all records
        • detect and standardise column names (API names vary)
        • remove exact duplicates
        • parse date column to datetime
        • coerce rainfall column to float64
        • flag and NaN-out negative values
        • filter District == Mandi (Python-level, case-insensitive)
        • sort chronologically
        • log missing value summary
  6.  Saves cleaned dataset as parquet + CSV.
  7.  Writes metadata.json.

What this collector does NOT do
────────────────────────────────
  ✗  No feature engineering
  ✗  No normalization or scaling
  ✗  No ML labels
  ✗  No merging with other sources
  ✗  No imputation of missing values

How to get API key
──────────────────
  1. Go to https://data.gov.in
  2. Click Register → fill name, email, mobile → verify email
  3. Login → click your name (top right) → My Account
  4. Scroll to API Keys → click Generate Key → copy key
  5. Paste key in config.yaml under api_keys.datagov

The key from your working URL is already set in config.yaml.

Output files
────────────
  datasets/datagov/raw/datagov_mandi_<YYYY>_raw.json      ← per year raw
  datasets/datagov/raw/datagov_mandi_all_raw.parquet       ← consolidated raw
  datasets/datagov/cleaned/datagov_mandi_cleaned.parquet
  datasets/datagov/cleaned/datagov_mandi_cleaned.csv
  datasets/datagov/metadata.json
  datasets/datagov/logs/datagov_collector_<YYYYMMDD>.log

Usage
─────
  # From project root:
  python -m collectors.datagov_collector

  # Programmatic:
  from collectors.datagov_collector import DataGovCollector
  collector = DataGovCollector()
  collector.run()
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterator

import pandas as pd
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.config_loader   import get_config, get_source_dir, get_date_range
from utils.logger          import get_logger
from utils.http_client     import build_session, get_timeout
from utils.metadata_writer import write_metadata


# ── Module constants ────────────────────────────────────────────
SOURCE_KEY     = "datagov"
COLLECTOR_NAME = "datagov_collector"
POLITENESS_DELAY = 1.0   # seconds between paginated requests (be polite to govt API)


class DataGovCollector:
    """
    Downloads daily district-wise rainfall data for Mandi district
    from the data.gov.in OGD API (NRSC VIC MODEL dataset).

    All configuration driven by config/config.yaml.
    No arguments required to instantiate or run.
    """

    def __init__(self) -> None:
        self._cfg        = get_config()
        self._src_cfg    = self._cfg["sources"][SOURCE_KEY]
        self._loc        = self._cfg["location"]
        self._source_dir = get_source_dir(SOURCE_KEY)
        self._raw_dir    = self._source_dir / "raw"
        self._clean_dir  = self._source_dir / "cleaned"
        self._log_dir    = self._source_dir / "logs"

        for d in (self._raw_dir, self._clean_dir, self._log_dir):
            d.mkdir(parents=True, exist_ok=True)

        self._logger  = get_logger(COLLECTOR_NAME, source_log_dir=self._log_dir)
        self._session = build_session()
        self._timeout = get_timeout()

        self._api_key    = self._cfg["api_keys"]["datagov"]
        self._base_url   = self._src_cfg["base_url"]
        self._resource_id = self._src_cfg["resource_id"]
        self._page_size  = int(self._src_cfg.get("page_size", 1000))

        self._start_date, self._end_date = get_date_range()
        self._district   = self._loc["district"]          # "Mandi"
        self._state      = self._loc["state"]             # "Himachal Pradesh"

        # API-level filter fields from config
        self._api_filters      = self._src_cfg.get("api_filters", {})
        self._year_field       = self._src_cfg.get("year_filter_field", "Year")
        self._dist_field       = self._src_cfg.get("district_filter_field", "District")
        self._dist_value       = self._src_cfg.get("district_filter_value", "Mandi")
        self._known_cols       = self._src_cfg.get("known_columns", {})

    # ══════════════════════════════════════════════════════════
    #  PUBLIC ENTRY POINT
    # ══════════════════════════════════════════════════════════

    def run(self) -> Path:
        """
        Execute the full data.gov.in collection pipeline:
            download → raw save → clean → cleaned save → metadata

        Returns
        -------
        Path to the cleaned parquet file.
        """
        self._logger.info("=" * 70)
        self._logger.info("DataGov NRSC VIC MODEL Collector — START")
        self._logger.info(f"Source      : {self._src_cfg['name']}")
        self._logger.info(f"Resource ID : {self._resource_id}")
        self._logger.info(f"API URL     : {self._base_url}/{self._resource_id}")
        self._logger.info(f"Location    : {self._district}, {self._state}")
        self._logger.info(f"Period      : {self._start_date.year} → {self._end_date.year}")
        self._logger.info(f"Page size   : {self._page_size}")
        self._logger.info("=" * 70)

        self._validate_api_key()

        # Step 1: Download year by year
        all_records: list[dict] = []
        years = list(range(self._start_date.year, self._end_date.year + 1))

        for year in tqdm(years, desc="Downloading years", unit="year"):
            year_records = self._download_year(year)
            if year_records:
                all_records.extend(year_records)
                self._save_raw_json(year_records, year)
                self._logger.info(f"  Year {year}: {len(year_records):,} records downloaded")
            else:
                self._logger.warning(f"  Year {year}: no records returned")

        if not all_records:
            msg = (
                "DataGov collector returned zero records across all years. "
                "Check API key, resource ID, and filter values in config.yaml."
            )
            self._logger.error(msg)
            raise RuntimeError(msg)

        self._logger.info(f"Total raw records across all years: {len(all_records):,}")

        # Step 2: Build raw DataFrame and save consolidated parquet
        df_raw      = pd.DataFrame(all_records)
        raw_path    = self._save_raw_parquet(df_raw)

        # Step 3: Clean
        df_cleaned  = self._clean(df_raw)

        # Step 4: Save cleaned
        cleaned_parquet, cleaned_csv = self._save_cleaned(df_cleaned)

        # Step 5: Write metadata
        meta_path = write_metadata(
            source_dir        = self._source_dir,
            source_name       = self._src_cfg["name"],
            api_url           = f"{self._base_url}/{self._resource_id}",
            update_frequency  = self._src_cfg["update_frequency"],
            df_cleaned        = df_cleaned,
            raw_file_path     = raw_path,
            cleaned_file_path = cleaned_parquet,
            extra={
                "resource_id":          self._resource_id,
                "agency":               "NRSC VIC MODEL",
                "ministry":             "Ministry of Jal Shakti / NWIC",
                "api_filters_applied":  self._api_filters,
                "district_filter":      f"{self._dist_field} == {self._dist_value}",
                "years_downloaded":     years,
                "total_raw_records":    len(all_records),
                "source_priority":      "Secondary — Government OGD Portal",
            },
        )

        self._logger.info("=" * 70)
        self._logger.info("DataGov NRSC VIC MODEL Collector — COMPLETE")
        self._logger.info(f"Cleaned rows    : {len(df_cleaned):,}")
        self._logger.info(f"Cleaned parquet : {cleaned_parquet}")
        self._logger.info(f"Cleaned CSV     : {cleaned_csv}")
        self._logger.info(f"Metadata        : {meta_path}")
        self._logger.info("=" * 70)

        return cleaned_parquet

    # ══════════════════════════════════════════════════════════
    #  VALIDATION
    # ══════════════════════════════════════════════════════════

    def _validate_api_key(self) -> None:
        """Check that a real API key is set. Fail fast with clear message."""
        if not self._api_key or self._api_key in (
            "YOUR_DATAGOV_API_KEY_HERE", "", None
        ):
            msg = (
                "\ndata.gov.in API key not set in config.yaml.\n"
                "Steps to get a key:\n"
                "  1. Go to https://data.gov.in\n"
                "  2. Click Register → fill details → verify email\n"
                "  3. Login → My Account → API Keys → Generate Key\n"
                "  4. Paste key in config.yaml under api_keys.datagov\n"
            )
            self._logger.error(msg)
            raise ValueError(msg)
        self._logger.info(f"API key loaded (first 8 chars): {self._api_key[:8]}...")

    # ══════════════════════════════════════════════════════════
    #  DOWNLOAD  (year-by-year with pagination)
    # ══════════════════════════════════════════════════════════

    def _download_year(self, year: int) -> list[dict[str, Any]]:
        """
        Download all paginated records for a single year.

        Strategy:
          1. Try with District filter at API level first (saves bandwidth).
          2. If API rejects district filter (returns 0 results or error),
             fall back to downloading all HP records and filtering in Python.

        Returns list of raw record dicts.
        """
        self._logger.info(f"  Downloading year {year}...")

        # Attempt 1: API-level district filter
        records = self._paginate(year, include_district_filter=True)

        if records:
            self._logger.info(
                f"  Year {year}: API district filter accepted — {len(records)} records"
            )
            return records

        # Attempt 2: Fallback — download all HP, filter in Python
        self._logger.warning(
            f"  Year {year}: API district filter returned 0 records. "
            f"Falling back to full HP download + Python filter."
        )
        all_hp_records = self._paginate(year, include_district_filter=False)

        if not all_hp_records:
            self._logger.warning(f"  Year {year}: No records even without district filter.")
            return []

        self._logger.info(
            f"  Year {year}: Downloaded {len(all_hp_records)} HP records. "
            f"Filtering for {self._district}..."
        )
        mandi_records = self._filter_district_python(all_hp_records)
        self._logger.info(
            f"  Year {year}: {len(mandi_records)} records after Python district filter."
        )
        return mandi_records

    def _paginate(
        self, year: int, include_district_filter: bool
    ) -> list[dict[str, Any]]:
        """
        Paginate through all pages for a given year.
        Returns a flat list of all record dicts.
        """
        all_records: list[dict] = []
        offset       = 0
        page_num     = 0
        total_count  = None   # learned from first response

        while True:
            page_num += 1
            params = self._build_params(year, offset, include_district_filter)

            response_data = self._fetch_page(params, year, page_num)

            if response_data is None:
                self._logger.error(
                    f"  Year {year}, page {page_num}: fetch failed. Stopping pagination."
                )
                break

            # Learn total count from first response
            if total_count is None:
                total_count = int(response_data.get("total", 0))
                if total_count == 0:
                    # No records for this year/filter combination
                    break
                self._logger.info(
                    f"  Year {year}: API reports {total_count:,} total records."
                )

            records = response_data.get("records", [])
            if not records:
                self._logger.info(
                    f"  Year {year}: empty page at offset {offset}. Pagination complete."
                )
                break

            all_records.extend(records)
            self._logger.debug(
                f"  Year {year}, page {page_num}: "
                f"got {len(records)} records (total so far: {len(all_records)})"
            )

            # Check if we've collected everything
            if len(all_records) >= total_count:
                self._logger.info(
                    f"  Year {year}: all {total_count} records collected."
                )
                break

            # Check if API returned a partial page (end of data)
            if len(records) < self._page_size:
                self._logger.info(
                    f"  Year {year}: partial page ({len(records)} < {self._page_size}). "
                    f"End of data."
                )
                break

            offset += self._page_size
            time.sleep(POLITENESS_DELAY)

        return all_records

    def _build_params(
        self, year: int, offset: int, include_district_filter: bool
    ) -> dict[str, Any]:
        """Build the API query parameters dict for one page request."""
        params: dict[str, Any] = {
            "api-key": self._api_key,
            "format":  "json",
            "limit":   self._page_size,
            "offset":  offset,
        }

        # Year filter
        params[f"filters[{self._year_field}]"] = str(year)

        # Static filters from config (State, Agency_name)
        for field, value in self._api_filters.items():
            params[f"filters[{field}]"] = value

        # Optional district filter
        if include_district_filter:
            params[f"filters[{self._dist_field}]"] = self._dist_value

        return params

    def _fetch_page(
        self, params: dict, year: int, page_num: int
    ) -> dict[str, Any] | None:
        """
        Fetch a single page from the API.
        Handles retries, rate limits, timeouts, and parse errors.
        Returns parsed JSON dict or None on failure.
        """
        url          = f"{self._base_url}/{self._resource_id}"
        max_retries  = int(self._cfg["http"]["max_retries"])
        backoff      = float(self._cfg["http"]["backoff_factor"])

        for attempt in range(1, max_retries + 2):
            try:
                resp = self._session.get(url, params=params, timeout=self._timeout)

                # Rate limit handling
                if resp.status_code == 429:
                    wait = backoff ** attempt
                    self._logger.warning(
                        f"  Year {year}, page {page_num}: "
                        f"rate limited (429). Waiting {wait:.0f}s (attempt {attempt})..."
                    )
                    time.sleep(wait)
                    continue

                # Client errors (4xx) other than 429 — don't retry
                if 400 <= resp.status_code < 500:
                    self._logger.error(
                        f"  Year {year}, page {page_num}: "
                        f"client error {resp.status_code}. "
                        f"Response: {resp.text[:300]}"
                    )
                    return None

                resp.raise_for_status()

                try:
                    data = resp.json()
                except ValueError as exc:
                    self._logger.error(
                        f"  Year {year}, page {page_num}: "
                        f"JSON parse error: {exc}. Body: {resp.text[:200]}"
                    )
                    return None

                # Check API-level error messages
                if data.get("status") == "error":
                    self._logger.error(
                        f"  Year {year}, page {page_num}: "
                        f"API returned error: {data.get('message', 'unknown')}"
                    )
                    return None

                return data

            except Exception as exc:
                wait = backoff ** attempt
                self._logger.warning(
                    f"  Year {year}, page {page_num}: "
                    f"request failed (attempt {attempt}/{max_retries + 1}): "
                    f"{type(exc).__name__}: {exc}. Retrying in {wait:.0f}s..."
                )
                time.sleep(wait)

        self._logger.error(
            f"  Year {year}, page {page_num}: all retries exhausted. Giving up."
        )
        return None

    # ══════════════════════════════════════════════════════════
    #  PYTHON-LEVEL DISTRICT FILTER
    # ══════════════════════════════════════════════════════════

    def _filter_district_python(
        self, records: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Filter records for Mandi district using Python (case-insensitive).
        Tries every plausible district column name from config known_columns.
        """
        if not records:
            return []

        dist_candidates = self._known_cols.get("district", ["District", "district"])
        target = self._dist_value.upper()

        for col in dist_candidates:
            if col in records[0]:
                filtered = [
                    r for r in records
                    if str(r.get(col, "")).strip().upper() == target
                ]
                self._logger.debug(
                    f"  Python district filter on column '{col}': "
                    f"{len(records)} → {len(filtered)} records"
                )
                return filtered

        self._logger.warning(
            f"  No district column found in records. "
            f"Tried: {dist_candidates}. "
            f"Available keys: {list(records[0].keys()) if records else '[]'}. "
            f"Returning all records unfiltered."
        )
        return records

    # ══════════════════════════════════════════════════════════
    #  BASIC CLEANING  (strictly no feature engineering)
    # ══════════════════════════════════════════════════════════

    def _clean(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Apply basic data quality steps only.

        Steps
        ─────
        1.  Log all raw column names (important — API names can vary)
        2.  Detect and standardise column names using known_columns from config
        3.  Remove exact duplicate rows
        4.  Parse date column to datetime
        5.  Coerce rainfall column to float64
        6.  Flag and NaN-out negative rainfall values
        7.  Apply Python-level district filter (safety net)
        8.  Sort chronologically by date
        9.  Log missing value summary

        Does NOT
        ─────────
        - Impute any missing values
        - Create derived or engineered columns
        - Normalize, scale, or transform values
        - Compute departure from normal
        """
        self._logger.info("Cleaning: starting basic cleaning pipeline...")
        df = df.copy()
        original_rows = len(df)

        # ── Step 1: Log raw columns ────────────────────────────
        self._logger.info(f"Cleaning: raw columns from API: {list(df.columns)}")

        # ── Step 2: Standardise column names ──────────────────
        df = self._standardise_columns(df)
        self._logger.info(f"Cleaning: standardised columns: {list(df.columns)}")

        # ── Step 3: Remove duplicates ──────────────────────────
        dupe_count = df.duplicated().sum()
        if dupe_count > 0:
            self._logger.warning(
                f"Cleaning: removing {dupe_count} exact duplicate rows."
            )
            df = df.drop_duplicates()

        # ── Step 4: Parse date column ──────────────────────────
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
            nat_count = df["date"].isna().sum()
            if nat_count > 0:
                self._logger.warning(
                    f"Cleaning: {nat_count} unparseable date values (set to NaT)."
                )
        else:
            self._logger.warning(
                "Cleaning: no 'date' column found after standardisation. "
                "Check known_columns.date in config.yaml."
            )

        # ── Step 5: Coerce rainfall to float64 ────────────────
        if "rainfall_mm" in df.columns:
            before_nulls = int(df["rainfall_mm"].isna().sum())
            df["rainfall_mm"] = pd.to_numeric(df["rainfall_mm"], errors="coerce")
            after_nulls = int(df["rainfall_mm"].isna().sum())
            new_nulls   = after_nulls - before_nulls
            if new_nulls > 0:
                self._logger.warning(
                    f"Cleaning: {new_nulls} rainfall values could not be coerced → NaN."
                )
            df["rainfall_mm"] = df["rainfall_mm"].astype("float64")
        else:
            self._logger.warning(
                "Cleaning: no 'rainfall_mm' column found. "
                "Check known_columns.rainfall in config.yaml."
            )

        # ── Step 6: Flag negative rainfall ────────────────────
        if "rainfall_mm" in df.columns:
            neg_mask  = df["rainfall_mm"] < 0
            neg_count = int(neg_mask.sum())
            if neg_count > 0:
                self._logger.warning(
                    f"Cleaning: {neg_count} negative rainfall values → set to NaN. "
                    f"Do NOT impute at this stage."
                )
                df.loc[neg_mask, "rainfall_mm"] = float("nan")

        # ── Step 7: Python-level district safety filter ────────
        if "district" in df.columns:
            before = len(df)
            df = df[
                df["district"].str.strip().str.upper() == self._district.upper()
            ].copy()
            after = len(df)
            if before != after:
                self._logger.info(
                    f"Cleaning: district safety filter: {before} → {after} rows "
                    f"(kept only '{self._district}')."
                )
        else:
            self._logger.warning(
                "Cleaning: no 'district' column — skipping district safety filter."
            )

        # ── Step 8: Sort by date ───────────────────────────────
        if "date" in df.columns:
            df = df.sort_values("date").reset_index(drop=True)

        # ── Step 9: Missing value summary ─────────────────────
        self._logger.info("Cleaning: missing value summary:")
        for col in df.columns:
            n   = int(df[col].isna().sum())
            pct = n / len(df) * 100 if len(df) > 0 else 0
            line = f"  {col:<30}: {n:>6} missing ({pct:.2f}%)"
            if n > 0:
                self._logger.warning(line)
            else:
                self._logger.info(line)

        self._logger.info(
            f"Cleaning complete. Input: {original_rows:,} rows → "
            f"Output: {len(df):,} rows."
        )
        return df

    def _standardise_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Rename raw API column names to a standard schema using known_columns from config.
        Standard names: date, district, state, rainfall_mm, agency, year

        Columns not in the mapping are kept as-is (prefixed with 'raw_').
        """
        rename_map: dict[str, str] = {}
        known = self._known_cols

        for standard_name, candidates in known.items():
            # Map standard_name keys to output column names
            output_name = {
                "date":     "date",
                "district": "district",
                "state":    "state",
                "rainfall": "rainfall_mm",
                "agency":   "agency",
                "year":     "year",
            }.get(standard_name, standard_name)

            for candidate in candidates:
                if candidate in df.columns:
                    rename_map[candidate] = output_name
                    break

        # Rename known columns
        df = df.rename(columns=rename_map)

        # Prefix any remaining unmapped columns with 'raw_' for transparency
        standard_set = {"date", "district", "state", "rainfall_mm", "agency", "year"}
        extra_cols   = [c for c in df.columns if c not in standard_set]
        if extra_cols:
            extra_rename = {c: f"raw_{c}" for c in extra_cols}
            df = df.rename(columns=extra_rename)
            self._logger.info(
                f"Cleaning: unmapped columns prefixed with 'raw_': {extra_cols}"
            )

        return df

    # ══════════════════════════════════════════════════════════
    #  SAVE
    # ══════════════════════════════════════════════════════════

    def _save_raw_json(self, records: list[dict], year: int) -> Path:
        """Save a single year's raw API records as JSON."""
        path = self._raw_dir / f"datagov_mandi_{year}_raw.json"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(records, fh, indent=2, ensure_ascii=False, default=str)
        size_kb = path.stat().st_size / 1024
        self._logger.info(f"Raw JSON saved: {path.name} ({size_kb:.1f} KB)")
        return path

    def _save_raw_parquet(self, df: pd.DataFrame) -> Path:
        """Save the consolidated raw DataFrame as parquet."""
        path = self._raw_dir / "datagov_mandi_all_raw.parquet"
        df.to_parquet(path, index=False, engine="pyarrow")
        size_kb = path.stat().st_size / 1024
        self._logger.info(
            f"Raw consolidated parquet saved: {path.name} "
            f"({size_kb:.1f} KB, {len(df):,} rows)"
        )
        return path

    def _save_cleaned(self, df: pd.DataFrame) -> tuple[Path, Path]:
        """Save the cleaned DataFrame as parquet and CSV."""
        parquet_path = self._clean_dir / "datagov_mandi_cleaned.parquet"
        csv_path     = self._clean_dir / "datagov_mandi_cleaned.csv"

        df.to_parquet(parquet_path, index=False, engine="pyarrow")
        df.to_csv(csv_path, index=False)

        size_kb = parquet_path.stat().st_size / 1024
        self._logger.info(f"Cleaned parquet : {parquet_path} ({size_kb:.1f} KB)")
        self._logger.info(f"Cleaned CSV     : {csv_path}")

        return parquet_path, csv_path


# ══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    collector = DataGovCollector()
    collector.run()
