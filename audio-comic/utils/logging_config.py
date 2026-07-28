"""Logging configuration for Audio-Comic Offline System.

Provides dual-output logging (console + file) with per-project log files,
log rotation, and structured format including timestamps and module names.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


# Module-level logger
_root_logger_configured = False

# Default format
LOG_FORMAT = "%(asctime)s | %(name)-25s | %(levelname)-8s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(
    log_dir: Optional[Path] = None,
    console_level: str = "INFO",
    file_level: str = "DEBUG",
    max_file_size_mb: int = 10,
    backup_count: int = 3,
) -> logging.Logger:
    """Configure the root logger with console and optional file handlers.

    Args:
        log_dir: Directory for log files. If None, only console logging.
        console_level: Minimum log level for console output.
        file_level: Minimum log level for file output.
        max_file_size_mb: Maximum size of each log file in MB.
        backup_count: Number of rotated log backups to keep.

    Returns:
        The configured root logger.
    """
    global _root_logger_configured

    root_logger = logging.getLogger("audio_comic")

    if _root_logger_configured:
        return root_logger

    root_logger.setLevel(logging.DEBUG)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, console_level.upper(), logging.INFO))
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    root_logger.addHandler(console_handler)

    # File handler (if directory provided)
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "audio_comic.log"

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_file_size_mb * 1024 * 1024,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(getattr(logging, file_level.upper(), logging.DEBUG))
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
        root_logger.addHandler(file_handler)

    _root_logger_configured = True
    return root_logger


def setup_project_logging(
    project_log_dir: Path,
    project_id: str,
) -> logging.Logger:
    """Create a project-specific logger that writes to the project's log directory.

    Args:
        project_log_dir: Path to the project's logs/ subdirectory.
        project_id: Unique project identifier for the logger name.

    Returns:
        A logger specific to this project.
    """
    project_log_dir.mkdir(parents=True, exist_ok=True)
    log_file = project_log_dir / "project.log"

    logger = logging.getLogger(f"audio_comic.project.{project_id}")
    logger.setLevel(logging.DEBUG)

    # Avoid duplicate handlers on re-initialization
    if not logger.handlers:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=5 * 1024 * 1024,
            backupCount=2,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
        logger.addHandler(file_handler)

    return logger


def get_logger(module_name: str) -> logging.Logger:
    """Get a child logger for a specific module.

    Args:
        module_name: Dot-separated module name (e.g., 'tts.vieneu_provider').

    Returns:
        A child logger under the audio_comic namespace.
    """
    return logging.getLogger(f"audio_comic.{module_name}")
