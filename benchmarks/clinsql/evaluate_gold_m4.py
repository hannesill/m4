"""Evaluate ClinSQL BigQuery gold-truth queries through the M4 (DuckDB) backend.

Reads clinsql.csv, translates each BigQuery gold SQL to DuckDB-compatible SQL,
executes it through the M4 Python API, and writes an updated CSV with an
'm4_gold_result' column alongside the original BigQuery 'gold_result'.

Usage:
    python evaluate_gold_m4.py
    python evaluate_gold_m4.py --split validation
    python evaluate_gold_m4.py --problem-id 001
    python evaluate_gold_m4.py --dry-run          # show translated SQL without executing
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR / "data"
INPUT_CSV = DATA_DIR / "clinsql.csv"
OUTPUT_CSV = DATA_DIR / "clinsql_with_m4.csv"

# ── BigQuery → DuckDB table name mapping ──────────────────────────────────────

TABLE_MAP = {
    "physionet-data.mimiciv_3_1_hosp": "mimiciv_hosp",
    "physionet-data.mimiciv_3_1_icu": "mimiciv_icu",
    "physionet-data.mimiciv_derived": "mimiciv_derived",
    "physionet-data.mimiciv_3_1_derived": "mimiciv_derived",
}

# ── Helpers ───────────────────────────────────────────────────────────────────


def _find_matching_paren(sql: str, open_pos: int) -> int:
    """Find the closing paren that matches the opening paren at open_pos."""
    depth = 0
    i = open_pos
    while i < len(sql):
        if sql[i] == "(":
            depth += 1
        elif sql[i] == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _split_top_level_args(s: str) -> list[str]:
    """Split a string by commas, respecting nested parentheses."""
    args = []
    depth = 0
    current = []
    for ch in s:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            args.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        args.append("".join(current).strip())
    return args


# ── SQL Translation ──────────────────────────────────────────────────────────


def translate_bq_to_duckdb(sql: str) -> str:
    """Translate BigQuery SQL to DuckDB-compatible SQL."""
    result = sql

    # 1. Replace backtick-quoted table names
    #    `physionet-data.mimiciv_3_1_hosp.patients` → mimiciv_hosp.patients
    for bq_prefix, duckdb_schema in TABLE_MAP.items():
        result = re.sub(
            rf"`{re.escape(bq_prefix)}\.(\w+)`",
            rf"{duckdb_schema}.\1",
            result,
        )

    # 2. APPROX_QUANTILES(expr, N)[OFFSET(K)] → QUANTILE_CONT(expr, K/N)
    result = _translate_approx_quantiles(result)

    # 3. SAFE_DIVIDE(a, b) → (a) / NULLIF((b), 0)
    #    Run multiple passes to handle nested SAFE_DIVIDE calls.
    for _ in range(5):
        prev = result
        result = _translate_func_2arg(
            result, "SAFE_DIVIDE", lambda a, b: f"({a}) / NULLIF(({b}), 0)"
        )
        if result == prev:
            break

    # 4. DATETIME_DIFF/DATE_DIFF/TIMESTAMP_DIFF(end, start, UNIT)
    #    → date_diff('UNIT', start, end)
    #    Single pass to avoid re-translating already-translated output.
    result = _translate_diff_funcs(result)

    # 5. COUNTIF(cond) → SUM(CASE WHEN cond THEN 1 ELSE 0 END)
    result = _translate_countif(result)

    # 6. REGEXP_CONTAINS(str, r'pattern') → regexp_matches(str, 'pattern')
    result = _translate_regexp_contains(result)

    # 7. PERCENTILE_CONT (BigQuery syntax) → quantile_cont (DuckDB name)
    result = re.sub(
        r"\bPERCENTILE_CONT\s*\(", "quantile_cont(", result, flags=re.IGNORECASE
    )

    # 8. SAFE_CAST(expr AS type) → TRY_CAST(expr AS type)
    result = re.sub(r"\bSAFE_CAST\s*\(", "TRY_CAST(", result, flags=re.IGNORECASE)

    # 8. BigQuery types → DuckDB types
    result = re.sub(r"\bFLOAT64\b", "DOUBLE", result)
    result = re.sub(r"\bINT64\b", "BIGINT", result)
    # Only replace STRING when used as a type cast (after AS or in CAST)
    result = re.sub(r"\bAS\s+STRING\b", "AS VARCHAR", result, flags=re.IGNORECASE)

    # 9. STRUCT(val AS key, ...) → {'key': val, ...}
    result = _translate_struct(result)

    # 10. SPLIT(str, delim)[OFFSET(n)] → string_split(str, delim)[n+1]
    result = _translate_split(result)

    # 11. Array indexing: [OFFSET(n)] → [n+1] (remaining ones not caught by APPROX_QUANTILES)
    result = _translate_offset_indexing(result)

    # 12. DATETIME_ADD/TIMESTAMP_ADD(expr, interval) → date_add(expr, interval)
    #     DATETIME_SUB/TIMESTAMP_SUB(expr, interval) → (expr - interval)
    #     Note: DuckDB's date_sub() has different semantics, so we use direct subtraction.
    result = re.sub(r"\bDATETIME_ADD\s*\(", "date_add(", result, flags=re.IGNORECASE)
    result = re.sub(r"\bTIMESTAMP_ADD\s*\(", "date_add(", result, flags=re.IGNORECASE)
    result = _translate_func_2arg(result, "DATETIME_SUB", lambda a, b: f"({a} - {b})")
    result = _translate_func_2arg(result, "TIMESTAMP_SUB", lambda a, b: f"({a} - {b})")

    # 13. DATETIME(year, month, day, h, m, s) → make_timestamp(year, month, day, h, m, s)
    result = _translate_datetime_constructor(result)

    # 14. DATETIME_TRUNC(expr, UNIT) → date_trunc('UNIT', expr)  (arg order swap)
    result = _translate_datetime_trunc(result)

    # 15. UNNEST(array) AS name → UNNEST(array) AS _t(name) for DuckDB
    result = _translate_unnest_alias(result)

    # 16. STARTS_WITH is supported natively in DuckDB — no change needed.

    # 16. LOGICAL_OR → BOOL_OR, LOGICAL_AND → BOOL_AND
    result = re.sub(r"\bLOGICAL_OR\s*\(", "BOOL_OR(", result, flags=re.IGNORECASE)
    result = re.sub(r"\bLOGICAL_AND\s*\(", "BOOL_AND(", result, flags=re.IGNORECASE)

    # 17. SAFE_OFFSET(n) → n+1 (same as OFFSET but returns NULL on OOB — DuckDB returns NULL by default)
    def safe_offset_repl(m):
        n = int(m.group(1))
        return f"[{n + 1}]"

    result = re.sub(
        r"\[\s*SAFE_OFFSET\s*\(\s*(\d+)\s*\)\s*\]",
        safe_offset_repl,
        result,
        flags=re.IGNORECASE,
    )

    # 18. IN UNNEST(array) → = ANY(array) (DuckDB doesn't support IN UNNEST)
    result = re.sub(r"\bIN\s+UNNEST\s*\(", "= ANY(", result, flags=re.IGNORECASE)

    # 19. r'pattern' string prefix (BigQuery regex literal) → 'pattern'
    result = re.sub(r"\br'([^']*)'", r"'\1'", result)
    result = re.sub(r'\br"([^"]*)"', r"'\1'", result)

    return result


def _translate_approx_quantiles(sql: str) -> str:
    """Translate APPROX_QUANTILES to DuckDB quantile_cont.

    Two forms:
      APPROX_QUANTILES(expr, N)[OFFSET(K)]  → quantile_cont(expr, K/N)
      APPROX_QUANTILES(expr, N)             → quantile_cont(expr, [0/N, 1/N, ..., N/N])
    Also handles IGNORE NULLS suffix (DuckDB ignores nulls by default).
    """
    pattern = re.compile(r"APPROX_QUANTILES\s*\(", re.IGNORECASE)
    result = sql
    offset = 0

    while True:
        m = pattern.search(result, offset)
        if not m:
            break

        # Find the closing paren of APPROX_QUANTILES(...)
        open_pos = m.end() - 1  # position of '('
        close_pos = _find_matching_paren(result, open_pos)
        if close_pos == -1:
            offset = m.end()
            continue

        inner = result[open_pos + 1 : close_pos]
        args = _split_top_level_args(inner)
        if len(args) < 2:
            offset = m.end()
            continue

        expr = args[0]
        # Strip IGNORE NULLS from the N parameter
        n_str = re.sub(
            r"\s+IGNORE\s+NULLS\s*$", "", args[1].strip(), flags=re.IGNORECASE
        )
        n_buckets = int(n_str)

        # Look for [OFFSET(K)] after the closing paren
        after = result[close_pos + 1 :]
        offset_match = re.match(
            r"\s*\[\s*OFFSET\s*\(\s*(\d+)\s*\)\s*\]", after, re.IGNORECASE
        )

        if offset_match:
            # Single percentile extraction
            k = int(offset_match.group(1))
            quantile = round(k / n_buckets, 4)
            end_pos = close_pos + 1 + offset_match.end()
            replacement = f"quantile_cont({expr}, {quantile})"
        else:
            # Full array form — produce a list of quantile values
            quantiles = [round(i / n_buckets, 4) for i in range(n_buckets + 1)]
            q_list = "[" + ", ".join(str(q) for q in quantiles) + "]"
            end_pos = close_pos + 1
            replacement = f"quantile_cont({expr}, {q_list})"

        result = result[: m.start()] + replacement + result[end_pos:]
        offset = m.start() + len(replacement)

    return result


def _translate_func_2arg(sql: str, func_name: str, rewrite_fn) -> str:
    """Translate a 2-argument function using a rewrite function."""
    pattern = re.compile(rf"\b{func_name}\s*\(", re.IGNORECASE)
    result = sql
    offset = 0

    while True:
        m = pattern.search(result, offset)
        if not m:
            break

        open_pos = m.end() - 1
        close_pos = _find_matching_paren(result, open_pos)
        if close_pos == -1:
            offset = m.end()
            continue

        inner = result[open_pos + 1 : close_pos]
        args = _split_top_level_args(inner)
        if len(args) < 2:
            offset = m.end()
            continue

        replacement = rewrite_fn(args[0], args[1])
        result = result[: m.start()] + replacement + result[close_pos + 1 :]
        offset = m.start() + len(replacement)

    return result


def _translate_diff_funcs(sql: str) -> str:
    """BQ: (DATETIME_DIFF|DATE_DIFF|TIMESTAMP_DIFF)(end, start, UNIT)
    → DuckDB: date_diff('UNIT', start, end)

    Uses a single combined pattern to avoid re-translating output.
    """
    pattern = re.compile(
        r"\b(?:DATETIME_DIFF|DATE_DIFF|TIMESTAMP_DIFF)\s*\(", re.IGNORECASE
    )
    result = sql
    offset = 0

    while True:
        m = pattern.search(result, offset)
        if not m:
            break

        open_pos = m.end() - 1
        close_pos = _find_matching_paren(result, open_pos)
        if close_pos == -1:
            offset = m.end()
            continue

        inner = result[open_pos + 1 : close_pos]
        args = _split_top_level_args(inner)
        if len(args) != 3:
            offset = m.end()
            continue

        end_expr = args[0].strip()
        start_expr = args[1].strip()
        unit = args[2].strip()

        replacement = f"date_diff('{unit}', {start_expr}, {end_expr})"
        result = result[: m.start()] + replacement + result[close_pos + 1 :]
        offset = m.start() + len(replacement)

    return result


def _translate_countif(sql: str) -> str:
    """COUNTIF(cond) → SUM(CASE WHEN cond THEN 1 ELSE 0 END)"""
    pattern = re.compile(r"\bCOUNTIF\s*\(", re.IGNORECASE)
    result = sql
    offset = 0

    while True:
        m = pattern.search(result, offset)
        if not m:
            break

        open_pos = m.end() - 1
        close_pos = _find_matching_paren(result, open_pos)
        if close_pos == -1:
            offset = m.end()
            continue

        cond = result[open_pos + 1 : close_pos]
        replacement = f"SUM(CASE WHEN {cond} THEN 1 ELSE 0 END)"
        result = result[: m.start()] + replacement + result[close_pos + 1 :]
        offset = m.start() + len(replacement)

    return result


def _translate_regexp_contains(sql: str) -> str:
    """REGEXP_CONTAINS(str, pattern) → regexp_matches(str, pattern)"""
    result = re.sub(
        r"\bREGEXP_CONTAINS\s*\(", "regexp_matches(", sql, flags=re.IGNORECASE
    )
    return result


def _translate_struct(sql: str) -> str:
    """STRUCT(val AS key, ...) → {'key': val, ...}

    BigQuery syntax:  STRUCT(1 AS sort_key, 'foo' AS name)
    DuckDB syntax:    {'sort_key': 1, 'name': 'foo'}
    """
    pattern = re.compile(r"\bSTRUCT\s*\(", re.IGNORECASE)
    result = sql
    offset = 0

    while True:
        m = pattern.search(result, offset)
        if not m:
            break

        open_pos = m.end() - 1
        close_pos = _find_matching_paren(result, open_pos)
        if close_pos == -1:
            offset = m.end()
            continue

        inner = result[open_pos + 1 : close_pos]
        fields = _split_top_level_args(inner)

        pairs = []
        valid = True
        for field in fields:
            # Match "value AS key" pattern
            as_match = re.match(
                r"(.+?)\s+AS\s+(\w+)\s*$", field.strip(), re.IGNORECASE | re.DOTALL
            )
            if as_match:
                val = as_match.group(1).strip()
                key = as_match.group(2).strip()
                pairs.append(f"'{key}': {val}")
            else:
                valid = False
                break

        if valid and pairs:
            replacement = "{" + ", ".join(pairs) + "}"
            result = result[: m.start()] + replacement + result[close_pos + 1 :]
            offset = m.start() + len(replacement)
        else:
            # Positional STRUCT(a, b, c) → ROW(a, b, c)
            replacement = f"ROW({inner})"
            result = result[: m.start()] + replacement + result[close_pos + 1 :]
            offset = m.start() + len(replacement)

    return result


def _translate_datetime_constructor(sql: str) -> str:
    """DATETIME(year, month, day, h, m, s) → make_timestamp(year, month, day, h, m, s)

    BigQuery DATETIME() creates a datetime from integer components.
    DuckDB make_timestamp() does the same.
    """
    pattern = re.compile(r"\bDATETIME\s*\(", re.IGNORECASE)
    result = sql
    offset = 0

    while True:
        m = pattern.search(result, offset)
        if not m:
            break

        # Make sure this is the constructor form (not DATETIME_DIFF etc.)
        # Check it's not part of a longer identifier
        before = result[: m.start()]
        if before and re.search(r"\w$", before):
            offset = m.end()
            continue

        open_pos = m.end() - 1
        close_pos = _find_matching_paren(result, open_pos)
        if close_pos == -1:
            offset = m.end()
            continue

        inner = result[open_pos + 1 : close_pos]
        args = _split_top_level_args(inner)

        if len(args) == 1:
            # DATETIME(expr) is a type cast → CAST(expr AS TIMESTAMP)
            replacement = f"CAST({args[0]} AS TIMESTAMP)"
        elif len(args) < 3:
            offset = close_pos + 1
            continue
        else:
            # Constructor form has 3-6 args (year, month, day[, hour, minute, second])
            replacement = f"make_timestamp({inner})"
        result = result[: m.start()] + replacement + result[close_pos + 1 :]
        offset = m.start() + len(replacement)

    return result


def _translate_datetime_trunc(sql: str) -> str:
    """DATETIME_TRUNC(expr, UNIT) → date_trunc('UNIT', expr)

    BigQuery: DATETIME_TRUNC(charttime, HOUR)
    DuckDB:   date_trunc('HOUR', charttime)
    """
    pattern = re.compile(r"\bDATETIME_TRUNC\s*\(", re.IGNORECASE)
    result = sql
    offset = 0

    while True:
        m = pattern.search(result, offset)
        if not m:
            break

        open_pos = m.end() - 1
        close_pos = _find_matching_paren(result, open_pos)
        if close_pos == -1:
            offset = m.end()
            continue

        inner = result[open_pos + 1 : close_pos]
        args = _split_top_level_args(inner)
        if len(args) != 2:
            offset = m.end()
            continue

        expr = args[0].strip()
        unit = args[1].strip()

        replacement = f"date_trunc('{unit}', {expr})"
        result = result[: m.start()] + replacement + result[close_pos + 1 :]
        offset = m.start() + len(replacement)

    return result


def _translate_unnest_alias(sql: str) -> str:
    """UNNEST(array) AS name → UNNEST(array) AS _t(name) for DuckDB.

    BigQuery: FROM UNNEST(['a', 'b']) AS col_name
    DuckDB:   FROM UNNEST(['a', 'b']) AS _t(col_name)
    """
    pattern = re.compile(r"\bUNNEST\s*\(", re.IGNORECASE)
    result = sql
    offset = 0

    while True:
        m = pattern.search(result, offset)
        if not m:
            break

        open_pos = m.end() - 1
        close_pos = _find_matching_paren(result, open_pos)
        if close_pos == -1:
            offset = m.end()
            continue

        # Look for AS <identifier> after the closing paren
        after = result[close_pos + 1 :]
        as_match = re.match(r"(\s+AS\s+)(\w+)(\s|$|,|\))", after, re.IGNORECASE)
        if as_match:
            # Check it's not already AS t(name) form
            rest_after_id = after[as_match.end(2) :].lstrip()
            if not rest_after_id.startswith("("):
                alias = as_match.group(2)
                # Replace AS name with AS _t(name)
                new_after = f"{as_match.group(1)}_t({alias}){as_match.group(3)}"
                result = result[: close_pos + 1] + new_after + after[as_match.end() :]
                offset = close_pos + 1 + len(new_after)
                continue

        offset = close_pos + 1

    return result


def _translate_split(sql: str) -> str:
    """SPLIT(str, delim) → string_split(str, delim)"""
    result = re.sub(r"\bSPLIT\s*\(", "string_split(", sql, flags=re.IGNORECASE)
    return result


def _translate_offset_indexing(sql: str) -> str:
    """[OFFSET(n)] → [n+1] and [ORDINAL(n)] → [n] for remaining array indexing."""

    # [OFFSET(n)] — 0-based in BQ → 1-based in DuckDB
    def offset_repl(m):
        n = int(m.group(1))
        return f"[{n + 1}]"

    result = re.sub(
        r"\[\s*OFFSET\s*\(\s*(\d+)\s*\)\s*\]", offset_repl, sql, flags=re.IGNORECASE
    )

    # [ORDINAL(n)] — 1-based in BQ → 1-based in DuckDB (no change needed, just strip syntax)
    def ordinal_repl(m):
        n = int(m.group(1))
        return f"[{n}]"

    result = re.sub(
        r"\[\s*ORDINAL\s*\(\s*(\d+)\s*\)\s*\]",
        ordinal_repl,
        result,
        flags=re.IGNORECASE,
    )

    return result


# ── Execution ────────────────────────────────────────────────────────────────


def execute_via_m4(sql: str) -> pd.DataFrame:
    """Execute a SQL query through the M4 API and return results as DataFrame."""
    from m4 import execute_query, set_dataset

    set_dataset("mimic-iv")
    return execute_query(sql)


def main():
    parser = argparse.ArgumentParser(description="Evaluate gold SQL through M4 backend")
    parser.add_argument(
        "--split", choices=["validation", "test"], help="Filter by split"
    )
    parser.add_argument("--domain", help="Filter by domain")
    parser.add_argument("--difficulty", help="Filter by difficulty")
    parser.add_argument("--problem-id", help="Run a single problem ID")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show translated SQL without executing"
    )
    parser.add_argument("--input", type=Path, default=INPUT_CSV, help="Input CSV")
    parser.add_argument("--output", type=Path, default=OUTPUT_CSV, help="Output CSV")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from existing output (skip completed)",
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: {args.input} not found. Run load_dataset.py first.")
        raise SystemExit(1)

    df = pd.read_csv(args.input, dtype={"problem_id": str})

    # Apply filters
    if args.split:
        df = df[df["split"] == args.split]
    if args.domain:
        df = df[df["domain"] == args.domain]
    if args.difficulty:
        df = df[df["difficulty"] == args.difficulty]
    if args.problem_id:
        df = df[df["problem_id"] == args.problem_id]

    if df.empty:
        print("No queries match the given filters.")
        raise SystemExit(1)

    # Initialize m4_gold_result and m4_gold_error columns
    if "m4_gold_result" not in df.columns:
        df["m4_gold_result"] = None
    if "m4_gold_error" not in df.columns:
        df["m4_gold_error"] = None
    if "m4_gold_sql" not in df.columns:
        df["m4_gold_sql"] = None

    # Resume support: load existing results
    completed_ids = set()
    if args.resume and args.output.exists():
        existing = pd.read_csv(args.output, dtype={"problem_id": str})
        for _, row in existing.iterrows():
            key = f"{row.get('domain', '')}/{row.get('difficulty', '')}/{row.get('problem_id', '')}"
            if pd.notna(row.get("m4_gold_result")) or pd.notna(
                row.get("m4_gold_error")
            ):
                completed_ids.add(key)
                # Copy result into df
                mask = (
                    (df["domain"] == row["domain"])
                    & (df["difficulty"] == row["difficulty"])
                    & (df["problem_id"] == row["problem_id"])
                )
                if mask.any():
                    df.loc[mask, "m4_gold_result"] = row.get("m4_gold_result")
                    df.loc[mask, "m4_gold_error"] = row.get("m4_gold_error")
                    df.loc[mask, "m4_gold_sql"] = row.get("m4_gold_sql")
        print(f"Resuming: {len(completed_ids)} already completed")

    # Set up M4 once (not in dry-run)
    if not args.dry_run:
        from m4 import set_dataset

        set_dataset("mimic-iv")

    total = len(df)
    success = 0
    fail = 0
    skipped = 0

    for i, (idx, row) in enumerate(df.iterrows()):
        tag = (
            f"[{i + 1}/{total}] {row['domain']}/{row['difficulty']}/{row['problem_id']}"
        )
        key = f"{row['domain']}/{row['difficulty']}/{row['problem_id']}"

        if key in completed_ids:
            skipped += 1
            continue

        if pd.isna(row["gold_sql"]):
            print(f"{tag} — no gold SQL, skipping")
            skipped += 1
            continue

        # Translate
        translated = translate_bq_to_duckdb(row["gold_sql"])
        df.at[idx, "m4_gold_sql"] = translated

        if args.dry_run:
            print(f"{tag}")
            print(f"  Original:   {row['gold_sql'][:120]}...")
            print(f"  Translated: {translated[:120]}...")
            print()
            continue

        # Execute
        try:
            from m4 import execute_query

            result_df = execute_query(translated)
            result_json = result_df.to_json(orient="records")
            df.at[idx, "m4_gold_result"] = result_json
            success += 1
            print(f"{tag} — OK ({len(result_df)} rows)")
        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            df.at[idx, "m4_gold_error"] = error_msg
            fail += 1
            print(f"{tag} — FAIL: {error_msg[:200]}")

        # Save incrementally every 10 queries
        if (i + 1) % 10 == 0:
            df.to_csv(args.output, index=False)

    if not args.dry_run:
        df.to_csv(args.output, index=False)
        print(f"\nDone. Success: {success}, Failed: {fail}, Skipped: {skipped}")
        print(f"Output: {args.output}")
    else:
        print(f"Dry run complete. {total} queries shown.")


if __name__ == "__main__":
    main()
