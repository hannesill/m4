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

        Additionally, a reserved "__meta__" key holds task-level cohort
        diagnostics independent of any single value column:
          - truth_rows: number of rows in ground truth
          - agent_rows_raw: number of rows in the agent CSV (pre-dedup)
          - agent_unique_keys: number of distinct key tuples in agent output
          - agent_keys_in_truth: agent keys that also exist in ground truth
          - extra_keys: agent keys NOT present in ground truth (fabricated
            or out-of-cohort rows)
          - key_precision: agent_keys_in_truth / agent_unique_keys. Per-column
            match_rate is a recall-style metric (of truth rows, how many were
            correctly covered); key_precision is its precision complement
            (of agent rows, how many belong to the cohort at all). Inflated
            or hallucinated output is invisible to match_rate but shows up
            here.
    """
    tolerance = tolerance or {}
    agent_df = pd.read_csv(agent_output_path)
    truth_df = pd.read_csv(ground_truth_path)

    agent_rows_raw = len(agent_df)
    agent_dupes = int(agent_df.duplicated(subset=key_columns).sum())
    agent_df = agent_df.drop_duplicates(subset=key_columns, keep="first")

    # --- Key-level cohort diagnostics (precision complement to match_rate) ---
    truth_keys = set(
        map(tuple, truth_df[key_columns].itertuples(index=False, name=None))
    )
    agent_keys = set(
        map(tuple, agent_df[key_columns].itertuples(index=False, name=None))
    )
    agent_unique_keys = len(agent_keys)
    agent_keys_in_truth = len(agent_keys & truth_keys)
    extra_keys = agent_unique_keys - agent_keys_in_truth
    key_precision = (
        agent_keys_in_truth / agent_unique_keys if agent_unique_keys > 0 else 0.0
    )

    # Check which value columns exist in agent output before merging
    agent_has_column = {col: col in agent_df.columns for col in value_columns}

    # Merge: left join from truth to agent
    merged = truth_df.merge(
        agent_df,
        on=key_columns,
        suffixes=("_truth", "_agent"),
        how="left",
        indicator=True,
    )

    # Track which truth rows had no agent match (key not present in agent output)
    missing_mask = merged["_merge"] == "left_only"
    merged = merged.drop(columns=["_merge"])

    results = {}
    for col in value_columns:
        truth_col = f"{col}_truth" if f"{col}_truth" in merged.columns else col
        agent_col = f"{col}_agent" if f"{col}_agent" in merged.columns else col
        tol = tolerance.get(col, 0)

        if not agent_has_column[col]:
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

    # Reserved key (double-underscore) for task-level cohort diagnostics.
    # Callers that iterate over value_columns ignore this; callers that
    # want cohort precision read it directly.
    results["__meta__"] = {
        "truth_rows": len(truth_df),
        "agent_rows_raw": agent_rows_raw,
        "agent_unique_keys": agent_unique_keys,
        "agent_keys_in_truth": agent_keys_in_truth,
        "extra_keys": extra_keys,
        "key_precision": key_precision,
    }

    return results
