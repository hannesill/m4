#!/usr/bin/env python3
"""Small DuckDB CLI shim for benchmark containers.

The benchmark image installs the DuckDB Python package for evaluation, but
agent CLIs often reach for a `duckdb` shell command. This wrapper supports the
common non-interactive patterns used in the benchmark:

  duckdb database.duckdb "SELECT ..."
  echo "SELECT ..." | duckdb database.duckdb

It is intentionally minimal and does not try to emulate the full upstream
interactive shell.
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb


def _usage() -> int:
    print("Usage: duckdb [DATABASE] [SQL]", file=sys.stderr)
    return 2


def _looks_like_database(path_str: str) -> bool:
    path = Path(path_str)
    return path.exists() or path.suffix in {".duckdb", ".db"}


def _resolve_args(argv: list[str]) -> tuple[str | None, str | None]:
    if not argv:
        return None, None
    if len(argv) == 1:
        first = argv[0]
        if _looks_like_database(first):
            return first, None
        return None, first
    return argv[0], argv[1]


def _print_rows(cursor: duckdb.DuckDBPyConnection) -> None:
    if cursor.description is None:
        return
    columns = [column[0] for column in cursor.description]
    rows = cursor.fetchall()
    print("\t".join(columns))
    for row in rows:
        print("\t".join("" if value is None else str(value) for value in row))


def main() -> int:
    db_path, sql = _resolve_args(sys.argv[1:])
    if len(sys.argv) > 3:
        return _usage()

    if sql is None and not sys.stdin.isatty():
        sql = sys.stdin.read()

    if not sql:
        return _usage()

    try:
        connection = duckdb.connect(database=db_path or ":memory:")
        cursor = connection.execute(sql)
        _print_rows(cursor)
        connection.close()
        return 0
    except Exception as exc:
        print(f"duckdb: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
