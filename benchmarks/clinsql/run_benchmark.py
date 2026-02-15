"""Run ClinSQL benchmark queries through Claude Code and collect responses.

Usage:
    python run_benchmark.py --split validation
    python run_benchmark.py --split validation --domain Laboratory_Results_Analysis
    python run_benchmark.py --problem-id 003
    python run_benchmark.py --split test --model opus --max-turns 15

Expects clinsql_with_m4.csv to exist (run load_dataset.py + evaluate_gold_m4.py first).
Results are saved incrementally — safe to interrupt and resume.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
INPUT_CSV = SCRIPT_DIR / "clinsql_with_m4.csv"

PROMPT_TEMPLATE = """\
You are a clinical data analyst expert specializing in the MIMIC-IV database.
Your goal is to correctly answer clinical questions about the MIMIC-IV database.
The SQL dialect is DuckDB.

M4 SQL API:
```python
from m4 import set_dataset, get_schema, get_table_info, execute_query

set_dataset("mimic-iv")                         # Must call first
schema = get_schema()                           # Returns {{'tables': list[str]}}
info = get_table_info("mimiciv_hosp.patients")  # Returns {{'schema': DataFrame, 'sample': DataFrame}}
df = execute_query("SELECT COUNT(*) FROM mimiciv_hosp.patients")  # Returns pd.DataFrame
```
All table names use `schema.table` format (e.g., `mimiciv_hosp.patients`, `mimiciv_icu.icustays`).

Clinical question:
"{question}"

Compute your answer in as few queries as possible; avoid exploratory dumps of reference tables.
Your final message must contain ONLY the line: FINAL ANSWER: <value>
"""


def _clean_trace(trace: list[dict]) -> list[dict]:
    """Strip noisy metadata from trace events, keeping only what's useful for review.

    Keeps: assistant reasoning, tool calls, tool results, final answer, cost summary.
    Removes: token usage, cache metrics, UUIDs, session IDs, redundant fields.
    """
    cleaned = []
    for event in trace:
        etype = event.get("type")

        if etype == "system":
            # Keep only model and tools from init
            cleaned.append(
                {
                    "type": "system",
                    "model": event.get("model"),
                    "tools": event.get("tools"),
                }
            )

        elif etype == "assistant":
            msg = event.get("message", {})
            content = msg.get("content", [])
            # Strip caller metadata from tool_use blocks
            slim_content = []
            for block in content:
                if block.get("type") == "tool_use":
                    slim_content.append(
                        {
                            "type": "tool_use",
                            "id": block.get("id"),
                            "name": block.get("name"),
                            "input": block.get("input"),
                        }
                    )
                elif block.get("type") == "text":
                    text = block.get("text", "").strip()
                    if text:
                        slim_content.append({"type": "text", "text": text})
            if slim_content:
                cleaned.append({"type": "assistant", "content": slim_content})

        elif etype == "user":
            msg = event.get("message", {})
            content = msg.get("content", [])
            slim_content = []
            for block in content:
                if block.get("type") == "tool_result":
                    entry = {
                        "type": "tool_result",
                        "tool_use_id": block.get("tool_use_id"),
                        "is_error": block.get("is_error", False),
                    }
                    # Use tool_use_result.stdout/stderr if available (cleaner),
                    # otherwise fall back to content string
                    tur = event.get("tool_use_result", {})
                    if isinstance(tur, dict) and (
                        tur.get("stdout") or tur.get("stderr")
                    ):
                        if tur.get("stdout"):
                            entry["stdout"] = tur["stdout"]
                        if tur.get("stderr"):
                            entry["stderr"] = tur["stderr"]
                    else:
                        raw = block.get("content", "")
                        if raw:
                            entry["content"] = raw
                    slim_content.append(entry)
            if slim_content:
                cleaned.append({"type": "user", "content": slim_content})

        elif etype == "result":
            cleaned.append(
                {
                    "type": "result",
                    "result": event.get("result"),
                    "is_error": event.get("is_error", False),
                    "num_turns": event.get("num_turns"),
                    "duration_ms": event.get("duration_ms"),
                    "total_cost_usd": event.get("total_cost_usd"),
                }
            )

    return cleaned


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


def run_query(
    question: str,
    model: str,
    max_turns: int,
    max_budget_usd: float | None,
) -> dict:
    """Call claude -p with a clinical question and return the parsed response."""
    work_dir = tempfile.mkdtemp(prefix="clinsql_work_")

    prompt = PROMPT_TEMPLATE.format(question=question)

    cmd = [
        "claude",
        "-p",
        "--output-format",
        "stream-json",
        "--model",
        model,
        "--max-turns",
        str(max_turns),
        "--no-session-persistence",
        "--verbose",
        "--tools",
        "Bash",
        "--disable-slash-commands",
        "--strict-mcp-config",
        "--mcp-config",
        '{"mcpServers":{}}',
        "--setting-sources",
        "",
        "--dangerously-skip-permissions",
    ]

    if max_budget_usd is not None:
        cmd += ["--max-budget-usd", str(max_budget_usd)]

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
        timeout=600,
        env=env,
        cwd=work_dir,
    )
    elapsed = time.time() - t0

    trace = []
    result_event = None
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
            trace.append(event)
            if event.get("type") == "result":
                result_event = event
        except json.JSONDecodeError:
            continue

    result = {
        "trace": trace,
        "raw_stderr": proc.stderr,
        "exit_code": proc.returncode,
        "elapsed_seconds": round(elapsed, 2),
    }

    if result_event:
        result["model_response"] = result_event.get("result", "")
        result["cost_usd"] = result_event.get("cost_usd")
        result["turns"] = result_event.get("num_turns")
    elif trace:
        for event in reversed(trace):
            if event.get("type") == "assistant":
                msg = event.get("message", {})
                content = msg.get("content", [])
                texts = [b.get("text", "") for b in content if b.get("type") == "text"]
                if texts:
                    result["model_response"] = "\n".join(texts)
                    break

    shutil.rmtree(work_dir, ignore_errors=True)
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Run ClinSQL benchmark through Claude Code"
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
    parser.add_argument(
        "--max-turns", type=int, default=10, help="Max agentic turns (default: 10)"
    )
    parser.add_argument(
        "--max-budget-usd", type=float, default=None, help="Max budget per query in USD"
    )
    parser.add_argument("--input", type=Path, default=INPUT_CSV, help="Input CSV")
    parser.add_argument("--output", type=Path, default=None, help="Output CSV")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: {args.input} not found. Run load_dataset.py first.")
        raise SystemExit(1)

    results_dir = SCRIPT_DIR / "results"
    output_csv = args.output or results_dir / f"clinsql_results_{args.model}.csv"
    traces_dir = results_dir / f"traces_{args.model}"

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

    print(f"Model: {args.model}, max turns: {args.max_turns}")
    print(f"Output: {output_csv}")
    print(f"Traces: {traces_dir}/")
    print(
        f"Total matching: {len(df)}, already completed: {len(df) - len(pending)}, to run: {len(pending)}"
    )
    print()

    for i, (_, row) in enumerate(pending.iterrows()):
        tag = f"[{i + 1}/{len(pending)}] {row.domain}/{row.difficulty}/{row.problem_id}"
        print(f"{tag} — running...")

        try:
            result = run_query(
                question=row["query"],
                model=args.model,
                max_turns=args.max_turns,
                max_budget_usd=args.max_budget_usd,
            )
        except subprocess.TimeoutExpired:
            result = {"model_response": "TIMEOUT", "elapsed_seconds": 600, "trace": []}
            print(f"{tag} — timed out")
        except Exception as e:
            result = {
                "model_response": f"ERROR: {e}",
                "elapsed_seconds": 0,
                "trace": [],
            }
            print(f"{tag} — error: {e}")

        trace_subdir = traces_dir / row["domain"] / row["difficulty"]
        trace_subdir.mkdir(parents=True, exist_ok=True)
        trace_file = trace_subdir / f"{row['problem_id']}.json"
        with open(trace_file, "w") as f:
            json.dump(_clean_trace(result.get("trace", [])), f, indent=2)

        out_row = {
            "split": row["split"],
            "domain": row["domain"],
            "difficulty": row["difficulty"],
            "problem_id": row["problem_id"],
            "query": row["query"],
            "gold_sql": row["gold_sql"],
            "gold_result": row["gold_result"],
            "m4_gold_result": row.get("m4_gold_result", ""),
            "model_response": result.get("model_response", ""),
            "cost_usd": result.get("cost_usd"),
            "turns": result.get("turns"),
            "elapsed_seconds": result.get("elapsed_seconds"),
            "exit_code": result.get("exit_code"),
            "trace_file": str(trace_file),
        }

        out_df = pd.DataFrame([out_row])
        header = not output_csv.exists()
        out_df.to_csv(output_csv, mode="a", header=header, index=False)

        status = (
            "ok" if result.get("exit_code") == 0 else f"exit={result.get('exit_code')}"
        )
        if not result.get("trace"):
            stderr_snip = (result.get("raw_stderr") or "")[:300]
            print(f"{tag} — WARNING: empty trace")
            if stderr_snip:
                print(f"  stderr: {stderr_snip}")
        print(f"{tag} — {status} ({result.get('elapsed_seconds', '?')}s)\n")

    print(f"\nDone. Results at {output_csv}")


if __name__ == "__main__":
    main()
