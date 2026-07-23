import yaml
from pathlib import Path

print("--- config/config.yaml relevant sections ---")
with open("config/config.yaml") as f:
    config = yaml.safe_load(f)

for key in ("study_area", "districts", "bounding_box", "bounding_boxes", "locations"):
    if key in config:
        print(f"{key}: {config[key]}")

print()
print("--- Searching for per-district raw collector output files ---")
for pattern in ["*mandi*", "*kullu*", "*chamba*"]:
    matches = list(Path("datasets").rglob(pattern))
    print(f"{pattern}: {len(matches)} matches")
    for m in matches[:10]:
        print("   ", m)
