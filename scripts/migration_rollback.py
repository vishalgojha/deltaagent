#!/usr/bin/env python3
"""Run a controlled Alembic downgrade for rollback procedures."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rollback Alembic migrations by revision or step count.")
    parser.add_argument(
        "--alembic-config",
        default="backend/db/alembic.ini",
        help="Path to Alembic config file.",
    )
    parser.add_argument(
        "--database-url",
        default="",
        help="Optional database URL override for the Alembic execution environment.",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=1,
        help="How many revisions to downgrade (ignored when --to-revision is provided).",
    )
    parser.add_argument(
        "--to-revision",
        default="",
        help="Explicit revision target to downgrade to.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the rollback command without executing it.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.steps < 1 and not args.to_revision:
        print("ERROR: --steps must be >= 1 when --to-revision is not set.")
        return 2

    target = args.to_revision.strip() or f"-{args.steps}"
    command = ["alembic", "-c", args.alembic_config, "downgrade", target]

    if args.database_url:
        os.environ["DATABASE_URL"] = args.database_url

    print(f"Rollback command: {' '.join(command)}")
    if args.dry_run:
        print("Dry-run mode enabled; no changes applied.")
        return 0

    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        print(f"ERROR: rollback failed with exit code {completed.returncode}")
        return completed.returncode

    print("Rollback completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

