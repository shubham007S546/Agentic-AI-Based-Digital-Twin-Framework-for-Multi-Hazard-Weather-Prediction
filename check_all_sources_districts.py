from pathlib import Path

sources = ["openmeteo", "imd", "nasa_gpm", "era5", "era5_land"]
districts = ["mandi", "kullu", "chamba"]

print("--- Directory structure under datasets/ ---")
for p in Path("datasets").iterdir():
    if p.is_dir():
        print(p)

print()
print("--- Per-source, per-district file counts ---")
for source in sources:
    for district in districts:
        matches = list(Path("datasets").rglob(f"*{source}*{district}*cleaned*"))
        if not matches:
            matches = list(Path("datasets").rglob(f"*{district}*")) 
            matches = [m for m in matches if source in str(m).lower()]
        print(f"{source} / {district}: {len(matches)} files")

print()
print("--- Sample: first openmeteo Kullu file (any) ---")
kullu_om = list(Path("datasets").rglob("*openmeteo*kullu*"))
print(kullu_om[:5])

print()
print("--- Sample: first IMD Kullu file (any) ---")
kullu_imd = list(Path("datasets").rglob("*imd*kullu*"))
print(kullu_imd[:5])
