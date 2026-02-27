#!/usr/bin/env python3
"""Precheck migration state before a release rollout."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text


def to_sync_url(url: str) -> str:
    return url.replace("+asyncpg", "").replace("+aiosqlite", "")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Alembic migration state against a database.")
    parser.add_argument(
        "--alembic-config",
        default="backend/db/alembic.ini",
        help="Path to Alembic config file.",
    )
    parser.add_argument(
        "--database-url",
        default="",
        help="Optional database URL override (falls back to DATABASE_URL env/alembic config).",
    )
    parser.add_argument(
        "--require-up-to-date",
        action="store_true",
        help="Fail if current DB revision is not exactly at Alembic head.",
    )
    return parser.parse_args()


def load_current_revisions(database_url: str) -> tuple[list[str], str | None]:
    engine = create_engine(database_url, future=True)
    try:
        with engine.connect() as conn:
            db_inspector = inspect(conn)
            if not db_inspector.has_table("alembic_version"):
                return [], "alembic_version table not found"
            rows = conn.execute(text("SELECT version_num FROM alembic_version")).all()
            revisions = [str(row[0]) for row in rows if row and row[0]]
            if not revisions:
                return [], "alembic_version table is empty"
            return revisions, None
    finally:
        engine.dispose()


def revision_ancestor_set(script: ScriptDirectory, head: str) -> set[str]:
    stack = [head]
    seen: set[str] = set()
    while stack:
        revision = stack.pop()
        if not revision or revision in seen:
            continue
        seen.add(revision)
        node = script.get_revision(revision)
        if node is None:
            continue
        down = node.down_revision
        if isinstance(down, tuple):
            stack.extend([item for item in down if item])
        elif down:
            stack.append(down)
    return seen


def main() -> int:
    args = parse_args()
    config_path = Path(args.alembic_config)
    if not config_path.exists():
        print(f"ERROR: Alembic config not found: {config_path}")
        return 2

    if args.database_url:
        os.environ["DATABASE_URL"] = args.database_url

    config = Config(str(config_path))
    script = ScriptDirectory.from_config(config)
    heads = set(script.get_heads())
    if not heads:
        print("ERROR: No Alembic heads found in migration scripts.")
        return 2

    raw_url = args.database_url or os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url")
    if not raw_url:
        print("ERROR: No database URL available for migration precheck.")
        return 2
    sync_url = to_sync_url(raw_url)

    current_revisions, error = load_current_revisions(sync_url)
    if error:
        print(f"ERROR: {error}. Run `alembic -c {config_path} upgrade head` first.")
        return 2

    unknown = [revision for revision in current_revisions if script.get_revision(revision) is None]
    if unknown:
        print(f"ERROR: Unknown DB revision(s): {', '.join(unknown)}")
        return 2

    ancestors: set[str] = set()
    for head in heads:
        ancestors |= revision_ancestor_set(script, head)
    disconnected = [revision for revision in current_revisions if revision not in ancestors]
    if disconnected:
        print(f"ERROR: Revision(s) not connected to migration graph heads: {', '.join(disconnected)}")
        return 2

    if args.require_up_to_date and set(current_revisions) != heads:
        print(
            "ERROR: Database is not at migration head. "
            f"current={current_revisions}, heads={sorted(heads)}"
        )
        return 2

    print("Migration precheck passed.")
    print(f"- Current revision(s): {current_revisions}")
    print(f"- Head revision(s): {sorted(heads)}")
    if set(current_revisions) != heads:
        print("- Note: DB is behind head but graph-compatible (allowed without --require-up-to-date).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

