import pandas as pd
import json

df = pd.read_parquet("datasets/merged_dataset/merged_dataset.parquet")

print("Index name:", df.index.name)
print("Index dtype:", df.index.dtype)
print("Index sample (first 3):", df.index[:3].tolist())
print("Index range:", df.index.min(), "to", df.index.max())

print()
print("--- merge_report.json ---")
with open("datasets/merged_dataset/merge_report.json") as f:
    report = json.load(f)
print(json.dumps(report, indent=2, default=str)[:3000])
