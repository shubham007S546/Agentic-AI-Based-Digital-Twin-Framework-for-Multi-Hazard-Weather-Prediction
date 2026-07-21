"""
utils/logger.py
───────────────
Logger factory used by every collector.
Each collector gets:
  1. A rotating file handler → logs/<source_name>_YYYYMMDD.log
  2. A source-local rotating file handler → datasets/<source>/logs/<source>_YYYYMMDD.log
  3. A console (stderr) handler

Usage:
    from utils.logger import get_logger
    logger = get_logger("imd_collector")
    logger.info("Starting download")
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from utils.config_loader import get_config, get_project_root


def get_logger(name: str, source_log_dir: Path | None = None) -> logging.Logger:
    """
    Build and return a named logger with rotating file + console handlers.

    Parameters
    ----------
    name : str
        Logger name (typically the collector module name, e.g. "imd_collector").
    source_log_dir : Path, optional
        If provided, adds a second rotating file handler inside the source's
        own logs/ directory.

    Returns
    -------
    logging.Logger
    """
    cfg      = get_config()
    log_cfg  = cfg["logging"]
    root_dir = get_project_root()

    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers if logger already configured
    if logger.handlers:
        return logger

    level = getattr(logging, log_cfg.get("level", "INFO").upper(), logging.INFO)
    logger.setLevel(level)

    formatter = logging.Formatter(
        fmt     = log_cfg.get("format",      "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"),
        datefmt = log_cfg.get("date_format", "%Y-%m-%d %H:%M:%S"),
    )

    max_bytes    = log_cfg.get("rotate_max_bytes",    10_485_760)
    backup_count = log_cfg.get("rotate_backup_count", 5)
    today        = datetime.now().strftime("%Y%m%d")

    # ── Handler 1: global project log ─────────────────────────
    global_log_dir = root_dir / log_cfg.get("global_log_dir", "logs")
    global_log_dir.mkdir(parents=True, exist_ok=True)
    global_log_path = global_log_dir / f"{name}_{today}.log"

    global_handler = RotatingFileHandler(
        filename    = global_log_path,
        maxBytes    = max_bytes,
        backupCount = backup_count,
        encoding    = "utf-8",
    )
    global_handler.setFormatter(formatter)
    global_handler.setLevel(level)
    logger.addHandler(global_handler)

    # ── Handler 2: source-local log ───────────────────────────
    if source_log_dir is not None:
        source_log_dir = Path(source_log_dir)
        source_log_dir.mkdir(parents=True, exist_ok=True)
        source_log_path = source_log_dir / f"{name}_{today}.log"

        source_handler = RotatingFileHandler(
            filename    = source_log_path,
            maxBytes    = max_bytes,
            backupCount = backup_count,
            encoding    = "utf-8",
        )
        source_handler.setFormatter(formatter)
        source_handler.setLevel(level)
        logger.addHandler(source_handler)

    # ── Handler 3: console ────────────────────────────────────
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    logger.addHandler(console_handler)

    logger.propagate = False
    return logger


# Convenience export for modules that rely on a shared logger instance.
# This preserves compatibility with older code that imported `logger`
# directly from utils.logger.
logger = get_logger("root")
