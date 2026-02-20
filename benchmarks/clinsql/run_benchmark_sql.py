"""Run ClinSQL benchmark in text-to-SQL mode: model outputs SQL, script executes it.

Usage:
    python run_benchmark_sql.py --split validation
    python run_benchmark_sql.py --split validation --domain Laboratory_Results_Analysis
    python run_benchmark_sql.py --problem-id 003
    python run_benchmark_sql.py --split test --model opus

Unlike run_benchmark.py (agentic mode where the model iteratively calls M4 tools),
this script asks the model to produce a single DuckDB SQL query, then executes it
through the M4 Python API and records both the SQL and the result.

Expects clinsql_with_m4.csv to exist (run load_dataset.py + evaluate_gold_m4.py first).
Results are saved incrementally — safe to interrupt and resume.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR / "data"
INPUT_CSV = DATA_DIR / "clinsql_with_m4.csv"
SCHEMA_FILE = DATA_DIR / "mimic4-schema.txt"

PROMPT_TEMPLATE = """\
You are a clinical data analyst expert specializing in the MIMIC-IV database.
Your goal is to write a single DuckDB SQL query that answers the clinical question below.

All table names use `schema.table` format (e.g., `mimiciv_hosp.patients`, `mimiciv_icu.icustays`).

Database schema:
{schema}

Clinical question:
"{question}"

Respond with ONLY a single SQL query inside a ```sql code block. No explanation, no commentary.
"""


def load_completed(output_csv: Path) -> set[str]:
    """Load problem IDs that have already been completed."""
    if not output_csv.exists():
        return set()
    df = pd.read_csv(
        output_csv,
        usecols=["problem_id", "domain", "difficulty"],
        dtype={"problem_id": str},
    )
    return {f"{r.domain}/{r.difficulty}/{r.problem_id}" for _, r in df.iterrows()}


def extract_sql(text: str) -> str | None:
    """Extract SQL from a ```sql code block, or fall back to the full text."""
    m = re.search(r"```sql\s*\n(.+?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    m = re.search(r"```\s*\n(.+?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # Fall back: if the whole response looks like SQL
    stripped = text.strip()
    if stripped.upper().startswith(("SELECT", "WITH")):
        return stripped
    return None


def generate_sql(
    question: str,
    model: str,
    schema_text: str,
) -> dict:
    """Call claude -p to generate a SQL query (no tools, single turn)."""
    prompt = PROMPT_TEMPLATE.format(question=question, schema=schema_text)

    cmd = [
        "claude",
        "-p",
        "--output-format",
        "stream-json",
        "--model",
        model,
        "--max-turns",
        "1",
        "--no-session-persistence",
        "--verbose",
        "--disable-slash-commands",
        "--strict-mcp-config",
        "--mcp-config",
        '{"mcpServers":{}}',
        "--setting-sources",
        "",
    ]

    env = os.environ.copy()
    for key in list(env):
        if key.startswith("CLAUDE"):
            del env[key]

    t0 = time.time()
    proc = subprocess.run(
        cmd,
        input=prompt,
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    elapsed = time.time() - t0

    result_event = None
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
            if event.get("type") == "result":
                result_event = event
        except json.JSONDecodeError:
            continue

    result = {
        "raw_stderr": proc.stderr,
        "exit_code": proc.returncode,
        "elapsed_seconds": round(elapsed, 2),
    }

    if result_event:
        result["model_response"] = result_event.get("result", "")
        result["cost_usd"] = result_event.get("cost_usd")

    return result


def execute_sql(sql: str) -> dict:
    """Execute a SQL query through the M4 Python API."""
    from m4 import execute_query, set_dataset

    set_dataset("mimic-iv")
    try:
        df = execute_query(sql)
        return {"success": True, "result": df.to_json(orient="records"), "error": None}
    except Exception as e:
        return {"success": False, "result": None, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(
        description="Run ClinSQL benchmark in text-to-SQL mode"
    )
    parser.add_argument(
        "--split", choices=["validation", "test"], help="Filter by split"
    )
    parser.add_argument(
        "--domain", help="Filter by domain (e.g. Laboratory_Results_Analysis)"
    )
    parser.add_argument(
        "--difficulty", help="Filter by difficulty (e.g. easy_level_queries)"
    )
    parser.add_argument("--problem-id", help="Run a single problem ID")
    parser.add_argument(
        "--model", default="sonnet", help="Model to use (default: sonnet)"
    )
    parser.add_argument("--input", type=Path, default=INPUT_CSV, help="Input CSV")
    parser.add_argument("--output", type=Path, default=None, help="Output CSV")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: {args.input} not found. Run load_dataset.py first.")
        raise SystemExit(1)

    schema_text = SCHEMA_FILE.read_text() if SCHEMA_FILE.exists() else ""
    if not schema_text:
        print(f"Warning: {SCHEMA_FILE} not found, prompts will lack schema context.")

    results_dir = SCRIPT_DIR / "results"
    output_csv = args.output or results_dir / f"clinsql_sql_results_{args.model}.csv"

    df = pd.read_csv(args.input, dtype={"problem_id": str})

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

    completed = load_completed(output_csv)
    pending = df[
        ~df.apply(
            lambda r: f"{r.domain}/{r.difficulty}/{r.problem_id}" in completed, axis=1
        )
    ]

    print("Mode: text-to-SQL")
    print(f"Model: {args.model}")
    print(f"Output: {output_csv}")
    print(
        f"Total matching: {len(df)}, already completed: {len(df) - len(pending)}, to run: {len(pending)}"
    )
    print()

    for i, (_, row) in enumerate(pending.iterrows()):
        tag = f"[{i + 1}/{len(pending)}] {row.domain}/{row.difficulty}/{row.problem_id}"
        print(f"{tag} — generating SQL...")

        try:
            gen = generate_sql(
                question=row["query"],
                model=args.model,
                schema_text=schema_text,
            )
        except subprocess.TimeoutExpired:
            gen = {"model_response": "TIMEOUT", "elapsed_seconds": 120}
            print(f"{tag} — generation timed out")
        except Exception as e:
            gen = {"model_response": f"ERROR: {e}", "elapsed_seconds": 0}
            print(f"{tag} — generation error: {e}")

        model_response = gen.get("model_response", "")
        generated_sql = extract_sql(model_response)

        # Execute the generated SQL
        exec_result = {"success": False, "result": None, "error": None}
        if generated_sql:
            print(f"{tag} — executing SQL...")
            exec_result = execute_sql(generated_sql)
            if not exec_result["success"]:
                print(f"{tag} — SQL error: {exec_result['error']}")
        else:
            exec_result["error"] = "Could not extract SQL from model response"
            print(f"{tag} — could not extract SQL from response")

        out_row = {
            "split": row["split"],
            "domain": row["domain"],
            "difficulty": row["difficulty"],
            "problem_id": row["problem_id"],
            "query": row["query"],
            "gold_sql": row["gold_sql"],
            "gold_result": row["gold_result"],
            "m4_gold_result": row.get("m4_gold_result", ""),
            "generated_sql": generated_sql or "",
            "model_result": exec_result["result"] or "",
            "sql_error": exec_result["error"] or "",
            "cost_usd": gen.get("cost_usd"),
            "elapsed_seconds": gen.get("elapsed_seconds"),
            "exit_code": gen.get("exit_code"),
        }

        out_df = pd.DataFrame([out_row])
        header = not output_csv.exists()
        out_df.to_csv(output_csv, mode="a", header=header, index=False)

        status = "ok" if exec_result["success"] else "FAIL"
        print(f"{tag} — {status} ({gen.get('elapsed_seconds', '?')}s)\n")

    print(f"\nDone. Results at {output_csv}")


if __name__ == "__main__":
    main()
