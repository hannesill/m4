"""Comparison utilities for evaluating agent output against ground truth."""

from __future__ import annotations

import pandas as pd


def compare_derived_tables(
    agent_output_path: str,
    ground_truth_path: str,
    key_columns: list[str],
    value_columns: list[str],
    tolerance: dict[str, float] | None = None,
) -> dict:
    """Compare agent output to ground truth CSV.

    Joins on key_columns, compares value_columns with optional per-column
    tolerance. Returns per-column match statistics.

    Args:
        agent_output_path: Path to agent's output CSV.
        ground_truth_path: Path to ground truth CSV.
        key_columns: Columns to join on (e.g., ["stay_id"]).
        value_columns: Columns to compare (e.g., ["sirs", "temp_score"]).
        tolerance: Per-column numeric tolerance. Default 0 (exact match).

    Returns:
        Dict keyed by column name, each containing:
          - match_rate: fraction of rows that match
          - total: total rows in ground truth
          - matched: number of matching rows
          - agent_rows: number of rows in agent output
          - missing_rows: rows in ground truth but not in agent output
          - mismatched_examples: up to 5 example mismatches
    """
    tolerance = tolerance or {}
    agent_df = pd.read_csv(agent_output_path)
    truth_df = pd.read_csv(ground_truth_path)

    agent_rows_raw = len(agent_df)
    agent_dupes = int(agent_df.duplicated(subset=key_columns).sum())
    agent_df = agent_df.drop_duplicates(subset=key_columns, keep="first")

    # Merge: left join from truth to agent
    merged = truth_df.merge(
        agent_df, on=key_columns, suffixes=("_truth", "_agent"), how="left"
    )

    # Track which truth rows had no agent match
    # (agent columns will be NaN for unmatched rows)
    first_value_col = value_columns[0]
    agent_col_name = f"{first_value_col}_agent"
    if agent_col_name in merged.columns:
        missing_mask = (
            merged[agent_col_name].isna() & merged[f"{first_value_col}_truth"].notna()
        )
    else:
        # Columns weren't renamed (no suffix needed if no overlap)
        missing_mask = pd.Series([False] * len(merged))

    results = {}
    for col in value_columns:
        truth_col = f"{col}_truth" if f"{col}_truth" in merged.columns else col
        agent_col = f"{col}_agent" if f"{col}_agent" in merged.columns else col
        tol = tolerance.get(col, 0)

        if agent_col not in merged.columns:
            results[col] = {
                "match_rate": 0.0,
                "total": len(truth_df),
                "matched": 0,
                "agent_rows": agent_rows_raw,
                "agent_duplicates": agent_dupes,
                "missing_rows": len(truth_df),
                "mismatched_examples": [],
                "error": f"Column '{col}' not found in agent output",
            }
            continue

        if tol == 0:
            matches = merged[truth_col] == merged[agent_col]
        else:
            matches = (merged[truth_col] - merged[agent_col]).abs() <= tol

        # Both NaN = match
        both_nan = merged[truth_col].isna() & merged[agent_col].isna()
        matches = matches | both_nan

        matched = int(matches.sum())
        total = len(merged)
        mismatched = merged[~matches].head(5)

        example_cols = [*key_columns]
        if truth_col in mismatched.columns:
            example_cols.append(truth_col)
        if agent_col in mismatched.columns:
            example_cols.append(agent_col)

        results[col] = {
            "match_rate": matched / total if total > 0 else 0.0,
            "total": total,
            "matched": matched,
            "agent_rows": agent_rows_raw,
            "agent_duplicates": agent_dupes,
            "missing_rows": int(missing_mask.sum()),
            "mismatched_examples": mismatched[example_cols].to_dict("records"),
        }

    return results
