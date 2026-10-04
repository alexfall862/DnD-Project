"""Launcher for the terminal harness: `python scripts/play.py --new` (or `make play`).
The harness itself is `backend/app/cli/play.py` and talks to the API over HTTP only."""

from __future__ import annotations

import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.insert(0, BACKEND)

from app.cli.play import main  # noqa: E402

if __name__ == "__main__":
    main()
