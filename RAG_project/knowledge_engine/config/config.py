import os
from pathlib import Path
from typing import Any, Dict

import yaml

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "knowledge_config.yaml"


def _resolve_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path


def load_config(config_path: Path = None) -> Dict[str, Any]:
    config_path = config_path or Path(os.environ.get("KNOWLEDGE_ENGINE_CONFIG", DEFAULT_CONFIG_PATH))
    if not config_path.exists():
        raise FileNotFoundError(f"Knowledge engine config not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    config: Dict[str, Any] = {
        "knowledge_root": _resolve_path(raw.get("knowledge_root", "knowledge_engine/knowledge")),
        "log_dir": _resolve_path(raw.get("log_dir", "knowledge_engine/logs")),
        "cache_dir": _resolve_path(raw.get("cache_dir", "knowledge_engine/cache")),
        "metadata_db": _resolve_path(raw.get("metadata_db", "knowledge_engine/metadata/knowledge_metadata.db")),
        "manifest_path": _resolve_path(raw.get("manifest_path", "knowledge_engine/statistics/knowledge_manifest.json")),
        "vectorstore_type": raw.get("vectorstore_type", "faiss"),
        "vectorstore_namespace": raw.get("vectorstore_namespace", "default"),
        "collections": raw.get("collections", {}),
        "collectors": raw.get("collectors", {}),
        "scheduler": raw.get("scheduler", {}),
        "logging": raw.get("logging", {}),
    }

    config["knowledge_root"].mkdir(parents=True, exist_ok=True)
    config["log_dir"].mkdir(parents=True, exist_ok=True)
    config["cache_dir"].mkdir(parents=True, exist_ok=True)
    config["metadata_db"].parent.mkdir(parents=True, exist_ok=True)
    config["manifest_path"].parent.mkdir(parents=True, exist_ok=True)

    return config


config = load_config()
