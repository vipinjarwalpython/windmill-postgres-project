import logging
import sys

from pythonjsonlogger import jsonlogger


def configure_logging(level: str) -> None:
    """Configure JSON logs so Docker, cloud logging, and local logs are machine-readable."""

    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s"
    )
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level.upper())
