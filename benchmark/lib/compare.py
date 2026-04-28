"""Comparison utilities for evaluating agent output against ground truth."""

from __future__ import annotations

import pandas as pd

NON_SCORING_REQUIRED_COLUMNS = {
    "subject_id",
    "hadm_id",
    "stay_id",
    "patientunitstayid",
    "patienthealthsystemstayid",
    "uniquepid",
}


def scored_value_columns(eval_config: dict) -> list[str]:
    """Return the clinical value columns that should affect task scoring.

    value_columns are always scored. Required clinical fields such as timestamps,
    labels, and intermediate values are also scored unless a task explicitly
    lists scored_columns. Stable identifiers are kept as schema/join columns and
    do not dilute the clinical reward.
    """
    if "scored_columns" in eval_config:
        return list(dict.fromkeys(eval_config["scored_columns"]))

    value_columns = list(eval_config["value_columns"])
    key_columns = set(eval_config.get("key_columns", []))
    required_columns = eval_config.get("required_columns", value_columns)
    non_scoring = (
        key_columns
        | NON_SCORING_REQUIRED_COLUMNS
        | set(eval_config.get("non_scoring_columns", []))
    )
    clinical_required = [
        col
        for col in required_columns
        if col not in non_scoring and col not in value_columns
    ]
    return list(dict.fromkeys([*value_columns, *clinical_required]))


def read_benchmark_csv(path: str) -> pd.DataFrame:
    """Read benchmark CSV while preserving literal clinical labels like "None"."""
    return pd.read_csv(path, keep_default_na=False, na_values=[""])


def _normalize_key_columns(df: pd.DataFrame, key_columns: list[str]) -> pd.DataFrame:
    """Normalize join keys so CSV parser dtype guesses do not change scoring."""
    normalized = df.copy()
    for col in key_columns:
        numeric = pd.to_numeric(normalized[col], errors="coerce")
        if numeric.notna().all():
            normalized[col] = numeric
            continue
        datetimes = pd.to_datetime(normalized[col], errors="coerce")
        if datetimes.notna().all():
            normalized[col] = datetimes
            continue
        normalized[col] = normalized[col].astype("string")
    return normalized


def _compare_values(
    truth: pd.Series, agent: pd.Series, tolerance: float | int | str
) -> pd.Series:
    """Compare values with numeric or timestamp tolerance where applicable."""
    truth_num = pd.to_numeric(truth, errors="coerce")
    agent_num = pd.to_numeric(agent, errors="coerce")
    truth_present = truth.notna()
    agent_present = agent.notna()
    comparable_present = truth_present & agent_present
    if (
        truth_num[truth_present].notna().all()
        and agent_num[comparable_present].notna().all()
    ):
        return (truth_num - agent_num).abs() <= float(tolerance or 0)

    truth_sample = truth[truth_present].astype("string").head(50)
    looks_temporal = truth_sample.str.contains(
        r"\d{4}-\d{2}-\d{2}|T\d{2}:|\d{1,2}:\d{2}", regex=True, na=False
    ).any()
    if not looks_temporal:
        return truth.astype("string") == agent.astype("string")

    truth_dt = pd.to_datetime(truth, errors="coerce")
    agent_dt = pd.to_datetime(agent, errors="coerce")
    if (
        truth_dt[truth_present].notna().all()
        and agent_dt[comparable_present].notna().all()
    ):
        tol = pd.to_timedelta(tolerance, unit="s", errors="coerce")
        if pd.isna(tol):
            tol = pd.Timedelta(0)
        return (truth_dt - agent_dt).abs() <= tol

    return truth.astype("string") == agent.astype("string")


def compare_derived_tables(
    agent_output_path: str,
    ground_truth_path: str,
    key_columns: list[str],
    value_columns: list[str],
    tolerance: dict[str, float] | None = None,
) -> dict:
    """Compare agent output to ground truth CSV.

    Joins on key_columns, compares value_columns with optional per-column
    tolerance. Missing truth keys, extra agent keys, and duplicate agent keys
    all count against the per-column match rate.

    Args:
        agent_output_path: Path to agent's output CSV.
        ground_truth_path: Path to ground truth CSV.
        key_columns: Columns to join on (e.g., ["stay_id"]).
        value_columns: Columns to compare (e.g., ["sirs", "temp_score"]).
        tolerance: Per-column numeric tolerance. Default 0 (exact match).

    Returns:
        Dict keyed by column name, each containing:
          - match_rate: fraction of rows that match
          - total: ground-truth rows plus extra and duplicate agent keys
          - matched: number of matching rows
          - agent_rows: number of rows in agent output
          - extra_rows: unique agent keys not present in ground truth
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
    agent_df = read_benchmark_csv(agent_output_path)
    truth_df = read_benchmark_csv(ground_truth_path)

    required_columns = set(key_columns) | set(value_columns)
    missing_agent_columns = [col for col in required_columns if col not in agent_df]
    missing_truth_columns = [col for col in required_columns if col not in truth_df]
    if missing_truth_columns:
        raise ValueError(
            "Ground truth missing required columns: "
            + ", ".join(sorted(missing_truth_columns))
        )
    if any(col not in agent_df for col in key_columns):
        raise ValueError(
            "Agent output missing key columns: "
            + ", ".join(col for col in key_columns if col not in agent_df)
        )

    truth_dupes = int(truth_df.duplicated(subset=key_columns).sum())
    if truth_dupes:
        raise ValueError(
            f"Ground truth contains {truth_dupes} duplicate key rows for "
            f"{', '.join(key_columns)}"
        )

    agent_df = _normalize_key_columns(agent_df, key_columns)
    truth_df = _normalize_key_columns(truth_df, key_columns)

    agent_rows_raw = len(agent_df)
    agent_dupes = int(agent_df.duplicated(subset=key_columns).sum())
    agent_df = agent_df.drop_duplicates(subset=key_columns, keep="first")
    truth_keys = truth_df[key_columns].drop_duplicates()
    agent_keys = agent_df[key_columns].drop_duplicates()
    extra_keys = agent_keys.merge(
        truth_keys, on=key_columns, how="left", indicator=True
    )
    extra_keys = extra_keys[extra_keys["_merge"] == "left_only"].drop(
        columns=["_merge"]
    )
    extra_rows = len(extra_keys)

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
    agent_has_column = {
        col: col in agent_df.columns and col not in missing_agent_columns
        for col in value_columns
    }

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
                "total": len(truth_df) + extra_rows + agent_dupes,
                "matched": 0,
                "agent_rows": agent_rows_raw,
                "agent_duplicates": agent_dupes,
                "extra_rows": extra_rows,
                "missing_rows": len(truth_df),
                "mismatched_examples": [],
                "error": f"Column '{col}' not found in agent output",
            }
            continue

        matches = _compare_values(merged[truth_col], merged[agent_col], tol)

        # Both NaN = match only when the agent supplied the key.  For a
        # left-join miss, the agent value is also NaN, but that is missing
        # output, not a correct null prediction.
        both_nan = merged[truth_col].isna() & merged[agent_col].isna() & ~missing_mask
        matches = matches | both_nan

        matched = int(matches.sum())
        total = len(merged) + extra_rows + agent_dupes
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
            "extra_rows": extra_rows,
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
