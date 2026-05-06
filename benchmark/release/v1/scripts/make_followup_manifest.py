#!/usr/bin/env python3
"""Generate canonical manifests for the May 6 validity follow-up runs.

The follow-up root intentionally retains retry/replacement directories for
audit. Paper analyses should use one canonical run per
task/condition/schema/model/trial key. This script selects the latest timestamped
run for each key, writes a canonical manifest, and records superseded duplicate
runs separately.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

M4_DIR = Path(
    os.environ.get("M4BENCH_M4_DIR", Path(__file__).resolve().parents[4])
).resolve()
PAPER_DIR = Path(
    os.environ.get("M4BENCH_PAPER_DIR", M4_DIR.parent / "m4bench-paper")
).resolve()
BENCHMARK_DIR = M4_DIR / "benchmark"
RESULTS_DIR = Path(
    os.environ.get("M4BENCH_RESULTS_DIR", BENCHMARK_DIR / "results")
).resolve()
PLANNING_DIR = PAPER_DIR / "planning"

FOLLOWUP_ROOT = RESULTS_DIR / "codex-validity-followup-20260506"
EXPECTED_ARTIFACTS = [
    "result.json",
    "output.csv",
    "instruction.md",
    "trace.jsonl",
    "egress.jsonl",
]


sys.path.insert(0, str(BENCHMARK_DIR))
from report_results import load_rows  # noqa: E402


def run_key(row: dict[str, Any]) -> tuple[str, str, str, str, int]:
    return (
        str(row["task"]),
        str(row["condition"]),
        str(row["schema"]),
        str(row["model"]),
        int(row["trial"]),
    )


def timestamp_key(row: dict[str, Any]) -> str:
    match = re.search(r"_(\d{8}_\d{6})$", str(row.get("run_id") or ""))
    return match.group(1) if match else ""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_entries(row: dict[str, Any]) -> list[dict[str, Any]]:
    run_path = Path(row["path"])
    entries = []
    for name in EXPECTED_ARTIFACTS:
        artifact = run_path / name
        if not artifact.exists():
            continue
        entries.append(
            {
                "artifact": name,
                "relative_path": str(artifact.relative_to(RESULTS_DIR)),
                "size_bytes": artifact.stat().st_size,
                "sha256": sha256_file(artifact),
            }
        )
    return entries


def row_record(row: dict[str, Any], *, status: str) -> dict[str, Any]:
    run_path = Path(row["path"])
    return {
        "status": status,
        "run_key": {
            "task": row["task"],
            "condition": row["condition"],
            "schema": row["schema"],
            "model": row["model"],
            "trial": int(row["trial"]),
        },
        "run_id": row["run_id"],
        "timestamp_key": timestamp_key(row),
        "relative_run_dir": str(run_path.relative_to(RESULTS_DIR)),
        "reward": row.get("reward"),
        "publishable": bool(row.get("publishable")),
        "isolated": bool(row.get("isolated")),
        "filesystem_canary": bool(row.get("filesystem_canary")),
        "contamination_lint": bool(row.get("contamination_lint")),
        "agent_returncode": row.get("agent_returncode"),
        "diagnostics_failed": bool(row.get("diagnostics_failed")),
        "passed": row.get("passed"),
        "failed": row.get("failed"),
        "errors": row.get("errors"),
        "artifact_count": len(artifact_entries(row)),
        "artifacts": artifact_entries(row),
    }


def canonicalize(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str, str, str, int], list[dict[str, Any]]] = defaultdict(
        list
    )
    for row in rows:
        grouped[run_key(row)].append(row)

    canonical = []
    superseded = []
    for key in sorted(grouped):
        candidates = sorted(
            grouped[key],
            key=lambda row: (timestamp_key(row), str(row.get("run_id") or "")),
        )
        winner = candidates[-1]
        canonical.append(winner)
        superseded.extend(candidates[:-1])
    return canonical, superseded


def write_csv_manifest(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "task",
        "condition",
        "schema",
        "model",
        "trial",
        "run_id",
        "relative_run_dir",
        "reward",
        "publishable",
        "isolated",
        "filesystem_canary",
        "contamination_lint",
        "agent_returncode",
        "diagnostics_failed",
        "passed",
        "failed",
        "errors",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            run_path = Path(row["path"])
            writer.writerow(
                {
                    "task": row["task"],
                    "condition": row["condition"],
                    "schema": row["schema"],
                    "model": row["model"],
                    "trial": int(row["trial"]),
                    "run_id": row["run_id"],
                    "relative_run_dir": str(run_path.relative_to(RESULTS_DIR)),
                    "reward": row.get("reward"),
                    "publishable": bool(row.get("publishable")),
                    "isolated": bool(row.get("isolated")),
                    "filesystem_canary": bool(row.get("filesystem_canary")),
                    "contamination_lint": bool(row.get("contamination_lint")),
                    "agent_returncode": row.get("agent_returncode"),
                    "diagnostics_failed": bool(row.get("diagnostics_failed")),
                    "passed": row.get("passed"),
                    "failed": row.get("failed"),
                    "errors": row.get("errors"),
                }
            )


def condition_schema_model_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter((row["condition"], row["schema"], row["model"]) for row in rows)
    return {
        f"{condition}/{schema}/{model}": count
        for (condition, schema, model), count in sorted(counts.items())
    }


def main() -> None:
    if not FOLLOWUP_ROOT.exists():
        raise FileNotFoundError(f"Follow-up root not found: {FOLLOWUP_ROOT}")

    PLANNING_DIR.mkdir(exist_ok=True)
    rows = load_rows(FOLLOWUP_ROOT)
    canonical, superseded = canonicalize(rows)

    manifest = {
        "generated_by": "benchmark/release/v1/scripts/make_followup_manifest.py",
        "source_root": str(FOLLOWUP_ROOT.relative_to(RESULTS_DIR)),
        "selection_rule": "For each task/condition/schema/model/trial key, select the run with the latest timestamp suffix in run_id; retain older same-key runs as superseded retries.",
        "raw_run_count": len(rows),
        "canonical_run_count": len(canonical),
        "superseded_run_count": len(superseded),
        "duplicate_extra_count": len(rows) - len(canonical),
        "canonical_counts": condition_schema_model_counts(canonical),
        "superseded_counts": condition_schema_model_counts(superseded),
        "canonical_runs": [
            row_record(row, status="canonical")
            for row in sorted(canonical, key=run_key)
        ],
    }
    superseded_manifest = {
        "generated_by": "benchmark/release/v1/scripts/make_followup_manifest.py",
        "source_root": str(FOLLOWUP_ROOT.relative_to(RESULTS_DIR)),
        "selection_rule": manifest["selection_rule"],
        "superseded_run_count": len(superseded),
        "superseded_runs": [
            row_record(row, status="superseded")
            for row in sorted(superseded, key=run_key)
        ],
    }

    canonical_path = PLANNING_DIR / "followup_canonical_manifest.json"
    superseded_path = PLANNING_DIR / "followup_superseded_runs.json"
    csv_path = PLANNING_DIR / "followup_canonical_runs.csv"
    summary_path = PLANNING_DIR / "followup_manifest_summary.md"

    canonical_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    superseded_path.write_text(
        json.dumps(superseded_manifest, indent=2, sort_keys=True)
    )
    write_csv_manifest(csv_path, sorted(canonical, key=run_key))

    strict_pass = sum(
        (row.get("failed") or 0) == 0 and (row.get("errors") or 0) == 0
        for row in canonical
    )
    publish_fail = sum(not row.get("publishable") for row in canonical)
    isolation_fail = sum(not row.get("isolated") for row in canonical)
    canary_fail = sum(not row.get("filesystem_canary") for row in canonical)
    lint_fail = sum(not row.get("contamination_lint") for row in canonical)
    nonzero_exit = sum(
        row.get("agent_returncode") not in {0, None, ""} for row in canonical
    )

    lines = [
        "# Follow-up Canonical Manifest Summary",
        "",
        "Generated by `benchmark/release/v1/scripts/make_followup_manifest.py`.",
        "",
        f"- Source root: `{FOLLOWUP_ROOT.relative_to(RESULTS_DIR)}`",
        f"- Raw result directories: {len(rows)}",
        f"- Canonical run keys: {len(canonical)}",
        f"- Superseded duplicate directories: {len(superseded)}",
        f"- Strict diagnostic passes among canonical runs: {strict_pass}/{len(canonical)}",
        f"- Canonical publishability failures: {publish_fail}",
        f"- Canonical isolation failures: {isolation_fail}",
        f"- Canonical filesystem-canary failures: {canary_fail}",
        f"- Canonical contamination-lint failures: {lint_fail}",
        f"- Canonical nonzero agent exits: {nonzero_exit}",
        "",
        "## Canonical Counts",
        "",
        "| Condition / schema / model | Runs |",
        "|---|---:|",
    ]
    for label, count in manifest["canonical_counts"].items():
        lines.append(f"| `{label}` | {count} |")
    lines += [
        "",
        "## Files",
        "",
        f"- Canonical manifest: `{canonical_path.relative_to(PAPER_DIR)}`",
        f"- Canonical CSV: `{csv_path.relative_to(PAPER_DIR)}`",
        f"- Superseded retry manifest: `{superseded_path.relative_to(PAPER_DIR)}`",
        "",
    ]
    summary_path.write_text("\n".join(lines))

    print(f"Wrote {canonical_path}")
    print(f"Wrote {csv_path}")
    print(f"Wrote {superseded_path}")
    print(f"Wrote {summary_path}")


if __name__ == "__main__":
    main()
