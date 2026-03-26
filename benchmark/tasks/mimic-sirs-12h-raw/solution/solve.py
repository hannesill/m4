"""Oracle solution: SIRS from raw tables, 12-hour window."""

import sys
from pathlib import Path

import duckdb

ORACLE_SQL = (
    Path(__file__).parent.parent.parent.parent / "oracle_sql" / "sirs_12h_raw.sql"
)


def solve(db_path: str, output_path: str) -> None:
    sql = ORACLE_SQL.read_text()
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
