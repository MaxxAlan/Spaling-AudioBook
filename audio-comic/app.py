"""CLI entry point for the audiobook audio subsystem."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main() -> None:
    """Run the audio CLI with UTF-8 console output."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    from utils.logging_config import setup_logging
    from utils.paths import get_app_root

    setup_logging(log_dir=get_app_root() / "logs")

    from cli import main as cli_main

    cli_main()


if __name__ == "__main__":
    main()
