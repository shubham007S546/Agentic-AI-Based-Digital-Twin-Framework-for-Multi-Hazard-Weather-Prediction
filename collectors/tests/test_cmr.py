"""
test_cmr.py — Run this FIRST before nasa_collector.
Tests CMR directly with no auth, no config, no complexity.

Run from project root:
    python test_cmr.py

Expected output if working:
    Status: 200
    Granules found: 48
    First granule: 3B-HHR-L.MS.MRG.3IMERG...
"""

import requests

CMR_URL = "https://cmr.earthdata.nasa.gov/search/granules.json"

# Test 1: Late Run (GPM_3IMERGHHL) — concept ID C2723754845-GES_DISC
print("=" * 60)
print("TEST 1: GPM Late Run via concept_id")
print("=" * 60)
r = requests.get(
    CMR_URL,
    params={
        "concept_id": "C2723754845-GES_DISC",
        "temporal":   "2024-01-01T00:00:00Z,2024-01-01T23:59:59Z",
        "page_size":  5,
    },
    headers={"Accept": "application/json"},
    timeout=30,
)
print(f"Status     : {r.status_code}")
data = r.json()
entries = data.get("feed", {}).get("entry", [])
print(f"Granules   : {len(entries)}")
if entries:
    print(f"First title: {entries[0].get('title', 'N/A')}")
    # Show download URL
    for link in entries[0].get("links", []):
        if link.get("href", "").endswith(".HDF5") and "#data" in link.get("rel", ""):
            print(f"HDF5 URL   : {link['href']}")
            break
else:
    print("NO GRANULES — CMR returned empty.")
    print("Raw response (first 500 chars):")
    print(r.text[:500])

print()

# Test 2: Final Run (GPM_3IMERGHH) — concept ID C2723754847-GES_DISC
print("=" * 60)
print("TEST 2: GPM Final Run via concept_id")
print("=" * 60)
r2 = requests.get(
    CMR_URL,
    params={
        "concept_id": "C2723754847-GES_DISC",
        "temporal":   "2024-01-01T00:00:00Z,2024-01-01T23:59:59Z",
        "page_size":  5,
    },
    headers={"Accept": "application/json"},
    timeout=30,
)
print(f"Status     : {r2.status_code}")
data2 = r2.json()
entries2 = data2.get("feed", {}).get("entry", [])
print(f"Granules   : {len(entries2)}")
if entries2:
    print(f"First title: {entries2[0].get('title', 'N/A')}")

print()

# Test 3: short_name instead of concept_id
print("=" * 60)
print("TEST 3: GPM Late Run via short_name + version")
print("=" * 60)
r3 = requests.get(
    CMR_URL,
    params={
        "short_name": "GPM_3IMERGHHL",
        "version":    "07",
        "provider":   "GES_DISC",
        "temporal":   "2024-01-01T00:00:00Z,2024-01-01T23:59:59Z",
        "page_size":  5,
    },
    headers={"Accept": "application/json"},
    timeout=30,
)
print(f"Status     : {r3.status_code}")
data3 = r3.json()
entries3 = data3.get("feed", {}).get("entry", [])
print(f"Granules   : {len(entries3)}")
if entries3:
    print(f"First title: {entries3[0].get('title', 'N/A')}")

print()
print("=" * 60)
print("SUMMARY")
print("=" * 60)
print(f"Late Run (concept_id) : {len(entries)}  granules")
print(f"Final Run (concept_id): {len(entries2)} granules")
print(f"Late Run (short_name) : {len(entries3)} granules")
print()
if len(entries) > 0 or len(entries3) > 0:
    print("✓ CMR is reachable and returning data.")
    print("  Use whichever test returned granules in your config.")
else:
    print("✗ ALL TESTS returned 0 granules.")
    print("  This means either:")
    print("  1. Your network blocks cmr.earthdata.nasa.gov")
    print("  2. CMR is temporarily down")
    print("  Run: curl 'https://cmr.earthdata.nasa.gov/search/granules.json?concept_id=C2723754845-GES_DISC&temporal=2024-01-01T00:00:00Z,2024-01-01T23:59:59Z&page_size=2'")
