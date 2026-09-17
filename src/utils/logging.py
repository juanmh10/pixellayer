"""
Logging Configuration
======================
Configures logging to stderr only (stdout is reserved for MCP stdio transport).
"""

from __future__ import annotations

import logging
import sys

from src.utils.config import config


def setup_logging(level: int = logging.INFO) -> None:
    """Configure logging to write to stderr and file in logs/.

    CRITICAL: Never log to stdout — it's used by MCP stdio transport.
    """
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Avoid duplicate handlers if setup_logging is called multiple times
    if not root_logger.handlers:
        # 1. Stderr handler
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setFormatter(formatter)
        root_logger.addHandler(stderr_handler)

        # 2. File handler in logs/ directory
        try:
            config.LOG_DIR.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(config.LOG_FILE, encoding="utf-8")
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        except Exception:
            pass  # Fallback gracefully to stderr if filesystem issue occurs

    # Suppress noisy third-party loggers
    logging.getLogger("transformers").setLevel(logging.WARNING)
    logging.getLogger("torch").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)
