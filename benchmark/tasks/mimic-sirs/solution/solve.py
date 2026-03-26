"""Oracle solution: run the canonical mimic-code SIRS SQL.

Usage:
    python benchmark/tasks/mimic-sirs/solution/solve.py <db_path> <output_path>
"""

import sys
from pathlib import Path

import duckdb

SKILL_SQL = (
    Path(__file__).parent.parent
    / "skills"
    / "sirs-criteria"
    / "scripts"
    / "mimic-iv.sql"
)


def solve(db_path: str, output_path: str) -> None:
    sql = SKILL_SQL.read_text()
    con = duckdb.connect(db_path, read_only=True)
    df = con.execute(sql).df()
    df.to_csv(output_path, index=False)
    print(f"Wrote {len(df)} rows to {output_path}")
    con.close()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <db_path> <output_path>")
        sys.exit(1)
    solve(sys.argv[1], sys.argv[2])
