import sys

from loguru import logger


def setup_logging() -> None:
    logger.remove()
    logger.add(
        sys.stdout,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <7} | {message}",
        level="INFO",
    )
