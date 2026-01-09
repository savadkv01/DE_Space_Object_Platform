# services/common/logging_utils.py
import logging
import sys
from typing import Optional, Dict, Any


LOG_FORMAT = (
    "%(asctime)s | %(levelname)s | %(name)s | "
    "run_id=%(run_id)s | component=%(component)s | %(message)s"
)


def get_logger(
    name: str,
    level: int = logging.INFO,
    fmt: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> logging.LoggerAdapter:
    """
    Create a structured logger.

    extra: default fields for all log records: e.g. {"component": "ingestion.nasa_neo.batch"}
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(fmt or LOG_FORMAT)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.propagate = False

    extra = extra or {}
    # default values to avoid KeyError in formatter
    extra.setdefault("run_id", "-")
    extra.setdefault("component", name)

    return logging.LoggerAdapter(logger, extra)
