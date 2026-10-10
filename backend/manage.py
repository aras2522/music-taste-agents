#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> None:
    backend = Path(__file__).resolve().parent
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Install project deps with `uv sync`."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
