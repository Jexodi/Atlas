import logging
import os
import tempfile
from pathlib import Path


def _get_logs_directory() -> Path:
    configured_directory = os.environ.get(
        "ATLAS_LOG_DIR",
        ""
    ).strip()

    if configured_directory:
        return Path(
            os.path.expandvars(
                configured_directory
            )
        ).expanduser()

    local_app_data = os.environ.get(
        "LOCALAPPDATA",
        ""
    ).strip()

    if local_app_data:
        return (
            Path(local_app_data)
            / "Atlas"
            / "logs"
        )

    return (
        Path(tempfile.gettempdir())
        / "Atlas"
        / "logs"
    )


def setup_logger(
    name: str = "atlas",
    level: int = logging.DEBUG
) -> logging.Logger:

    logs_directory = _get_logs_directory()
    logs_directory.mkdir(
        parents=True,
        exist_ok=True
    )

    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(level)

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] "
        "[%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(
        logs_directory / "atlas.log",
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger
