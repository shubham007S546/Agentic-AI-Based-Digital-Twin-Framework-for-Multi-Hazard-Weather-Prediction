import yaml, os, json, sys
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[1] / 'RAG_project' / 'knowledge_engine' / 'config' / 'knowledge_config.yaml'

if not CONFIG_PATH.exists():
    print(json.dumps({"error": "config_not_found", "path": str(CONFIG_PATH)}))
    sys.exit(1)

with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
    cfg = yaml.safe_load(f)

project_cfg = cfg.get('collectors', {}).get('project_repo', {})
root_dir = project_cfg.get('root_dir', '.')
ignore = set(project_cfg.get('ignore', []))
supported = set(project_cfg.get('supported_extensions', []))

repo_root = Path(__file__).resolve().parents[1]
scan_root = (repo_root / root_dir).resolve()

files = []
for dirpath, dirnames, filenames in os.walk(scan_root):
    # skip ignored dirs anywhere in path
    if any(part in ignore for part in Path(dirpath).parts):
        continue
    for fn in filenames:
        full = Path(dirpath) / fn
        ext = full.suffix.lower()
        # treat Dockerfile, requirements.txt, etc as extensions listed literally
        key = fn if fn in supported else ext
        if ext in supported or fn in supported:
            files.append({
                'path': str(full.relative_to(repo_root)),
                'name': fn,
                'ext': ext,
            })

# aggregate counts
from collections import Counter, defaultdict
ext_counts = Counter()
per_file = defaultdict(list)
for f in files:
    ext_counts[f['ext'] or f['name']] += 1
    per_file[f['ext'] or f['name']].append(f['path'])

out = {
    'config_path': str(CONFIG_PATH),
    'scan_root': str(scan_root),
    'total_candidates': len(files),
    'counts_by_ext': dict(ext_counts),
    'samples': {k: v[:10] for k, v in per_file.items()},
}
print(json.dumps(out, indent=2))
