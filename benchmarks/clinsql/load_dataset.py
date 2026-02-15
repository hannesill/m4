"""Load the ClinSQL HuggingFace dataset and enrich it with gold result CSVs.

Usage:
    python load_dataset.py [--splits-dir PATH]

Expects the ClinSQL data/splits/ directory to be copied into benchmarks/clinsql/.
Default layout:
    benchmarks/clinsql/
    ├── splits/          ← copied from ClinSQL repo data/splits/
    ├── load_dataset.py  ← this script
    └── clinsql.csv      ← output
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from datasets import load_dataset

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_SPLITS_DIR = SCRIPT_DIR / "splits"
OUTPUT_PATH = SCRIPT_DIR / "clinsql.csv"

# The result_path column in the HF dataset looks like:
#   data/splits/validation/Diagnostic_Procedures/easy_level_queries/001/result_001.csv
# We strip this prefix to resolve against --splits-dir.
RESULT_PATH_PREFIX = "data/splits/"


def read_gold_result(splits_dir: Path, result_path: str) -> str | None:
    """Read a gold result CSV and return its content as a JSON string."""
    rel = result_path.removeprefix(RESULT_PATH_PREFIX)
    csv_path = splits_dir / rel

    if not csv_path.exists():
        print(f"  MISSING: {csv_path}")
        return None

    df = pd.read_csv(csv_path)
    return df.to_json(orient="records")


def main():
    parser = argparse.ArgumentParser(description="Load ClinSQL and attach gold results")
    parser.add_argument(
        "--splits-dir",
        type=Path,
        default=DEFAULT_SPLITS_DIR,
        help=f"Path to the splits/ directory (default: {DEFAULT_SPLITS_DIR})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_PATH,
        help=f"Output CSV path (default: {OUTPUT_PATH})",
    )
    args = parser.parse_args()

    if not args.splits_dir.exists():
        print(f"Error: splits directory not found at {args.splits_dir}")
        print("Copy the ClinSQL repo's data/splits/ directory there first.")
        raise SystemExit(1)

    print("Loading ClinSQL dataset from HuggingFace...")
    ds = load_dataset("yifeis02/ClinSQL")

    rows = []
    for split_name in ["validation", "test"]:
        split = ds[split_name]
        print(f"Processing {split_name} split ({len(split)} rows)...")

        for i, row in enumerate(split):
            gold_result = read_gold_result(args.splits_dir, row["result_path"])
            rows.append(
                {
                    "split": row["split"],
                    "domain": row["domain"],
                    "difficulty": row["difficulty"],
                    "problem_id": row["problem_id"],
                    "query": row["query"],
                    "gold_sql": row["sql"],
                    "gold_result": gold_result,
                    "sql_rubric": row["sql_rubric"],
                    "results_rubric": row["results_rubric"],
                }
            )

    df = pd.DataFrame(rows)

    n_missing = df["gold_result"].isna().sum()
    n_total = len(df)
    print(f"\nGold results: {n_total - n_missing}/{n_total} found, {n_missing} missing")

    df.to_csv(args.output, index=False)
    print(f"Saved to {args.output} ({len(df)} rows)")


if __name__ == "__main__":
    main()
