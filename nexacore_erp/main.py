"""Command-line entry point for the NexaCore ERP package."""

from __future__ import annotations

import argparse
from typing import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    """Parse CLI arguments and dispatch to the requested workflow."""

    parser = argparse.ArgumentParser(
        prog="nexacore_erp",
        description=(
            "Run the NexaCore ERP desktop application or one of its helper "
            "utilities."
        ),
    )
    parser.add_argument(
        "--diag-db",
        action="store_true",
        help="Run the lightweight database diagnostics helper and exit.",
    )

    args = parser.parse_args(None if argv is None else list(argv))

    if args.diag_db:
        from diag_db import run as run_db_diagnostics

        run_db_diagnostics()
        return 0

    from .app import run_app

    run_app()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
