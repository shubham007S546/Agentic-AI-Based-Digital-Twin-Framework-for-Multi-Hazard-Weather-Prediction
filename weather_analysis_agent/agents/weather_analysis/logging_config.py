"""Shared logger for the weather analysis agent."""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

from .config import settings

_configured = False


def get_logger(name: str = "weather_analysis") -> logging.Logger:
    global _configured
    logger = logging.getLogger(name)

    if not _configured:
        os.makedirs(settings.log_dir, exist_ok=True)
        logger.setLevel(logging.INFO)

        fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        file_handler = RotatingFileHandler(
            os.path.join(settings.log_dir, "weather_analysis.log"),
            maxBytes=5_000_000, backupCount=3,
        )
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(fmt)
        logger.addHandler(console_handler)

        _configured = True

    return logger
