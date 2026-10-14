import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from core.config import Settings, get_settings


_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging(settings: Settings | None = None) -> logging.Logger:
    settings = settings or get_settings()
    logger = logging.getLogger("productivity")
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG if settings.debug else logging.INFO)
    formatter = logging.Formatter(_LOG_FORMAT)
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    log_path = Path(settings.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_path, maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.propagate = False
    return logger


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(f"productivity.{name}")
