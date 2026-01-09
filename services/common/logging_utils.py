import logging
import sys
from typing import Optional


def get_logger(
    name: str,
    level: int = logging.INFO,
    fmt: Optional[str] = None,
) -> logging.Logger:
    """
    Returns a logger with a standard format suitable for container logs.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.handlers:
        return logger  # already configured

    handler = logging.StreamHandler(sys.stdout)
    fmt = fmt or (
        "%(asctime)s | %(levelname)s | %(name)s | "
        "run_id=%(run_id)s | %(message)s"
    )
    formatter = logging.Formatter(fmt)
    handler.setFormatter(formatter)

    logger.addHandler(handler)
    logger.propagate = False
    return logger


class RunLoggerAdapter(logging.LoggerAdapter):
    """
    Adds `run_id` to log records for correlation across services.
    """

    def __init__(self, logger: logging.Logger, run_id: str):
        super().__init__(logger, extra={"run_id": run_id})

    def process(self, msg, kwargs):
        # Ensure run_id always present in extra
        kwargs.setdefault("extra", {})
        kwargs["extra"].setdefault("run_id", self.extra.get("run_id", "-"))
        return msg, kwargs