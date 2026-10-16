#!/usr/bin/env python3
"""Freeze the public manifest for the July 2026 full-coverage Claude campaign.

Inputs are private: the camera-ready audit directory (canonical 560-run
selection, collaborator archive metadata, recovered source provenance) and the
local results roots. Outputs are tracked release metadata under
`planning/claude28/` and contain no clinical rows, only run identity, evaluator
fields, recorded harness indicators, and artifact hashes.

This script freezes an existing selection; it does not select runs itself.
`make_claude28_tables.py` regenerates every Claude 28-task number from its
outputs.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from archive_io import iter_members, sha256_bytes, sha256_file
from sanitize_artifacts import redact_local_paths

M4_DIR = Path(
    os.environ.get("M4BENCH_M4_DIR", Path(__file__).resolve().parents[4])
).resolve()
PAPER_DIR = Path(
    os.environ.get("M4BENCH_PAPER_DIR", Path(__file__).resolve().parents[1])
).resolve()
RESULTS_DIR = Path(
    os.environ.get("M4BENCH_RESULTS_DIR", M4_DIR / "benchmark" / "results")
).resolve()
OUT_DIR = PAPER_DIR / "planning" / "claude28"

REQUIRED = [
    "result.json",
    "output.csv",
    "trace.jsonl",
    "instruction.md",
    "egress.jsonl",
]
MODEL_ALIASES = {"claude-opus-4-7": "opus", "claude-sonnet-4-6": "sonnet"}
LOCAL_ROOTS = {
    "rebuttal-claude-opus-sonnet-20260726": "canonical or overlapping local root",
    "rebuttal-claude-opus-sonnet-additional-20260728": "canonical or overlapping local root",
    "rebuttal-claude-opus-sonnet-20260726-quarantine-auth-revoked": "quarantined: authentication revoked during run",
    "rebuttal-claude-opus-sonnet-20260726-quarantine-runtime-failures": "quarantined: runtime failure or incomplete duplicate",
    "rebuttal-claude-opus-sonnet-additional-20260728-quarantine-runtime-failures": "quarantined: runtime failure or incomplete duplicate",
    "rebuttal-claude-opus-sonnet-canary-20260726": "isolation leak canary, not a task run",
}
TEST_FIELDS = [
    "passed",
    "failed",
    "errors",
    "total",
    "reward",
    "reward_uncapped",
    "diagnostics_failed",
    "key_precision",
    "extra_keys",
    "agent_unique_keys",
    "match_rates",
]
PROVENANCE_FILES = {
    # published name -> path relative to the audit directory
    "collaborator/code_diff.patch": "archive_metadata/hannes_evidence_20260929/code_diff.patch",
    "collaborator/code_provenance.json": "archive_metadata/hannes_evidence_20260929/code_provenance.json",
    "collaborator/launch_commands.md": "archive_metadata/hannes_evidence_20260929/launch_commands.md",
    "collaborator/finish_four_tasks.sh": "archive_metadata/hannes_evidence_20260929/finish_four_tasks.sh",
    "collaborator/finish_next_four_tasks.sh": "archive_metadata/hannes_evidence_20260929/finish_next_four_tasks.sh",
    "collaborator/finish_remaining_gaps.sh": "archive_metadata/hannes_evidence_20260929/finish_remaining_gaps.sh",
    "collaborator/finish_five_tasks.sh": "archive_metadata/hannes_evidence_20260929/finish_five_tasks.sh",
    "collaborator/campaign_manifest.json": "archive_metadata/claude-28-20260726/campaign_manifest.json",
    "collaborator/canonical_manifest.json": "archive_metadata/hannes_evidence_20260929/claude-28-20260726_canonical_manifest.json",
    "collaborator/patch_audit.json": "source_provenance/collaborator_patch_audit.json",
    "local/historical_commits.json": "source_provenance/historical_commits.json",
    "local/benchmark_source_hashes.json": "source_provenance/benchmark_source_hashes.json",
    "local/5f1faabb5a9a36ff72bff86ca29f714cdcdf09ff.patch": "source_provenance/5f1faabb5a9a36ff72bff86ca29f714cdcdf09ff.patch",
    "local/c38e0986df071aef712c323eb3fdbc1e75ded891.patch": "source_provenance/c38e0986df071aef712c323eb3fdbc1e75ded891.patch",
    "local/31fecb245ec91c80bbd2597a1a5ac356afe688cb.patch": "source_provenance/31fecb245ec91c80bbd2597a1a5ac356afe688cb.patch",
}
LOCAL_CAMPAIGN_FILES = ["campaign_manifest.json", "campaign_slice_manifest.json"]


def public_run(record: dict[str, Any]) -> dict[str, Any]:
    tests = record["test_results"]
    trace = record.get("trace_summary", {})
    run = {
        "run_id": record["run_id"],
        "task": record["task"],
        "condition": record["condition"],
        "schema": record["schema"],
        "agent": record["agent"],
        "requested_model": record["model"],
        "model_alias": record["model_alias"],
        "trial": record["trial"],
        "timestamp": record["timestamp"],
        "source": record["source"],
        "source_run_path": record["source_run_path"],
        "requested_reasoning_effort": record.get("reasoning_effort"),
        "resolved_reasoning_effort": record.get("resolved_reasoning_effort"),
        "publishable": record["publishable"],
        "isolated": record["isolated"],
        "filesystem_canary_passed": record["filesystem_canary"]["passed"],
        "contamination_lint_passed": record["contamination_lint"]["passed"],
        "agent_returncode": record["agent_result"]["returncode"],
        "test_results": {key: tests.get(key) for key in TEST_FIELDS},
        "recorded_model_overrides": record.get("claude_model_overrides"),
        "trace_observed": {
            "assistant_models": trace.get("assistant_models", []),
            "usage_models": trace.get("usage_models", []),
            "cli_versions": trace.get("cli_versions", []),
        },
        "artifacts": {
            name: {"sha256": item["sha256"], "size_bytes": item["bytes"]}
            for name, item in sorted(record["artifacts"].items())
        },
    }
    if record.get("declared_base_commit"):
        run["declared_base_commit"] = record["declared_base_commit"]
        run["commit_provenance"] = record["commit_provenance"]
    if record.get("source_archive"):
        run["source_archive"] = record["source_archive"]
    return run


def usage_fields(result: dict[str, Any]) -> dict[str, Any]:
    usage = result.get("token_usage") or {}
    return {
        "agent_elapsed_seconds": (result.get("agent_result") or {}).get(
            "elapsed_seconds"
        ),
        "token_usage": {
            key: usage.get(key)
            for key in ("input_tokens", "cached_input_tokens", "output_tokens", "turns")
        },
    }


def collaborator_results(archive: Path, wanted: set[str]) -> dict[str, dict[str, Any]]:
    """Read result.json of canonical collaborator runs from the archive stream."""
    found = {}
    for member, payload in iter_members(archive, lambda name: name in wanted):
        found[member.name.rsplit("/", 1)[0]] = json.loads(payload)
    missing = {name.rsplit("/", 1)[0] for name in wanted} - set(found)
    if missing:
        raise SystemExit(
            f"{len(missing)} collaborator result.json files missing from {archive}"
        )
    return found


def result_summary(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return {"result_json": f"unreadable: {type(exc).__name__}"}
    agent = data.get("agent_result") or {}
    tests = data.get("test_results") or {}
    return {
        "task": data.get("task"),
        "condition": data.get("condition"),
        "model": data.get("model"),
        "trial": data.get("trial"),
        "agent_returncode": agent.get("returncode"),
        "failure_reason": agent.get("failure_reason"),
        "reward": tests.get("reward"),
        "publishable": data.get("publishable"),
    }


def attempt_inventory(
    canonical_paths: set[str], collaborator_superseded: list[dict[str, Any]]
) -> dict[str, Any]:
    attempts = []
    for root, category in LOCAL_ROOTS.items():
        root_dir = RESULTS_DIR / root
        if not root_dir.is_dir():
            raise SystemExit(f"Missing local results root: {root_dir}")
        for run_dir in sorted(p for p in root_dir.iterdir() if p.is_dir()):
            relative = f"benchmark/results/{root}/{run_dir.name}"
            if relative in canonical_paths:
                continue
            record = {
                "run_dir": relative,
                "category": (
                    "non-canonical overlapping coverage (cross-cohort comparison only)"
                    if category.startswith("canonical")
                    else category
                ),
                "artifacts_present": sorted(
                    name for name in REQUIRED if (run_dir / name).is_file()
                ),
            }
            record.update(result_summary(run_dir / "result.json"))
            attempts.append(record)
    for item in collaborator_superseded:
        attempts.append(
            {
                "run_dir": f"claude-28-20260726/{item['run_id']}",
                "category": "collaborator superseded attempt (older same-cell attempt)",
                "task": item["task"],
                "condition": item["condition"],
                "model": item["model"],
                "trial": item["trial"],
                "agent_returncode": item["returncode"],
                "reward": item["reward"],
                "failure_reason": item.get("pytest_tail"),
                "artifacts_present": ["output.csv"]
                if item.get("has_output_csv")
                else [],
            }
        )
    counts = Counter(item["category"] for item in attempts)
    return {
        "description": (
            "Every retained July 2026 Claude attempt outside the canonical 560-run "
            "selection. These are provenance only and are excluded from analysis."
        ),
        "counts": dict(sorted(counts.items())),
        "known_gaps": [
            "A separate authentication-failure archive from the collaborator campaign "
            "(about 121 MB) was not retrieved; its failed attempts are not listed here.",
        ],
        "attempts": attempts,
    }


def copy_provenance(audit_dir: Path) -> list[dict[str, Any]]:
    index = []
    provenance_dir = OUT_DIR / "provenance"
    sources = {name: audit_dir / rel for name, rel in PROVENANCE_FILES.items()}
    for root in (
        "rebuttal-claude-opus-sonnet-20260726",
        "rebuttal-claude-opus-sonnet-additional-20260728",
    ):
        for filename in LOCAL_CAMPAIGN_FILES:
            sources[f"local/{root}/{filename}"] = RESULTS_DIR / root / filename
    for name, source in sorted(sources.items()):
        if not source.is_file():
            raise SystemExit(f"Missing provenance input: {source}")
        original = source.read_bytes()
        published = redact_local_paths(original.decode("utf-8")).encode("utf-8")
        destination = provenance_dir / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(published)
        index.append(
            {
                "published_path": f"provenance/{name}",
                "original_sha256": sha256_bytes(original),
                "published_sha256": sha256_bytes(published),
                "local_paths_redacted": published != original,
            }
        )
    return index


def write_runs_csv(path: Path, runs: list[dict[str, Any]]) -> None:
    columns = [
        "run_id",
        "task",
        "condition",
        "model_alias",
        "requested_model",
        "trial",
        "source",
        "source_run_path",
        "reward",
        "failed",
        "errors",
        "strict_pass",
        "key_precision",
        "extra_keys",
        "agent_unique_keys",
        "cli_versions",
        "assistant_models",
        "recorded_model_overrides",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for run in runs:
            tests = run["test_results"]
            writer.writerow(
                {
                    **{key: run[key] for key in columns[:7]},
                    "source_run_path": run["source_run_path"],
                    "reward": tests["reward"],
                    "failed": tests["failed"],
                    "errors": tests["errors"],
                    "strict_pass": tests["failed"] == 0 and tests["errors"] == 0,
                    "key_precision": tests["key_precision"],
                    "extra_keys": tests["extra_keys"],
                    "agent_unique_keys": tests["agent_unique_keys"],
                    "cli_versions": ";".join(run["trace_observed"]["cli_versions"]),
                    "assistant_models": ";".join(
                        run["trace_observed"]["assistant_models"]
                    ),
                    "recorded_model_overrides": bool(run["recorded_model_overrides"]),
                }
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--audit-dir",
        type=Path,
        default=RESULTS_DIR / "camera-ready-audit-20260930",
        help="Private camera-ready audit directory.",
    )
    parser.add_argument(
        "--collaborator-archive",
        type=Path,
        required=True,
        help="Collaborator run archive (read for elapsed time and token usage).",
    )
    args = parser.parse_args()
    audit_dir = args.audit_dir.resolve()

    private = json.loads((audit_dir / "canonical_rebuttal_manifest.json").read_text())
    audit = json.loads((audit_dir / "combined_rebuttal_audit.json").read_text())
    superseded = json.loads(
        (audit_dir / "collaborator_superseded_attempts.json").read_text()
    )
    if audit["issues"]:
        raise SystemExit("Audit reports unresolved issues; refusing to freeze.")
    runs = sorted(
        (public_run(record) for record in private["runs"]),
        key=lambda run: (
            run["task"],
            run["model_alias"],
            run["condition"],
            run["trial"],
        ),
    )
    cells: dict[tuple, list[int]] = defaultdict(list)
    for run in runs:
        cells[(run["task"], run["model_alias"], run["condition"])].append(run["trial"])
        if set(run["artifacts"]) != set(REQUIRED):
            raise SystemExit(f"{run['run_id']}: required artifact hashes missing")
    if (
        len(runs) != 560
        or len(cells) != 112
        or any(sorted(trials) != [1, 2, 3, 4, 5] for trials in cells.values())
    ):
        raise SystemExit(
            "Canonical selection is not 28 tasks x 2 models x 2 conditions x 5 trials"
        )

    # Local canonical artifacts are re-hashed; collaborator artifacts were hashed
    # from the archive during the audit and are re-verified by the packager.
    remote = collaborator_results(
        args.collaborator_archive,
        {
            f"{run['source_run_path']}/result.json"
            for run in runs
            if run["source"] == "Collaborator canonical archive"
        },
    )
    for run in runs:
        if run["source"] == "Collaborator canonical archive":
            run.update(usage_fields(remote[run["source_run_path"]]))
            continue
        run_dir = M4_DIR / run["source_run_path"]
        if not run_dir.is_dir():
            run_dir = RESULTS_DIR / Path(run["source_run_path"]).relative_to(
                "benchmark/results"
            )
        for name, expected in run["artifacts"].items():
            path = run_dir / name
            if (
                path.stat().st_size != expected["size_bytes"]
                or sha256_file(path) != expected["sha256"]
            ):
                raise SystemExit(f"Hash mismatch for {path}")
        run.update(usage_fields(json.loads((run_dir / "result.json").read_text())))

    archive = audit["archive"]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "campaign": "July 2026 full-coverage Claude native-schema replication",
        "selection_policy": private["selection_policy"],
        "design": "28 tasks x {opus, sonnet} x {no-skill, with-skill} x trials 1-5",
        "sources": {
            "collaborator_archive": {
                "filename": archive["archive_name"],
                "size_bytes": archive["archive_bytes"],
                "sha256": archive["archive_sha256"],
                "canonical_runs": sum(
                    r["source"].startswith("Collaborator") for r in runs
                ),
                "availability": "private; contains credentialed-data outputs",
            },
            "local_roots": dict(
                Counter(
                    Path(r["source_run_path"]).parts[2]
                    for r in runs
                    if r["source_run_path"].startswith("benchmark/results/")
                )
            ),
        },
        "bootstrap": audit["bootstrap"],
        "strict_pass_definition": "test_results.failed == 0 and test_results.errors == 0",
        "key_f1_definition": (
            "2 * (agent_unique_keys - extra_keys) / (agent_unique_keys + reference_rows), "
            "with reference_rows from tables/task_details.tex; reconstructed from retained "
            "evaluator counts, not a fresh evaluation of output CSVs"
        ),
        "harness_indicators": {
            "cli_versions": "Claude Code versions observed in trace.jsonl",
            "recorded_model_overrides": (
                "model-slot environment overrides recorded in result.json; null means "
                "no override was recorded and Claude Code native routing applied"
            ),
            "assistant_models": (
                "assistant models observed in trace events; native routing can add "
                "claude-haiku-4-5 calls to requested Opus/Sonnet runs"
            ),
        },
        "runs": runs,
    }
    (OUT_DIR / "claude28_canonical_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )
    write_runs_csv(OUT_DIR / "claude28_canonical_runs.csv", runs)
    canonical_paths = {run["source_run_path"] for run in runs}
    inventory = attempt_inventory(canonical_paths, superseded)
    (OUT_DIR / "claude28_attempt_inventory.json").write_text(
        json.dumps(inventory, indent=2) + "\n"
    )
    provenance = copy_provenance(audit_dir)
    (OUT_DIR / "provenance_index.json").write_text(
        json.dumps(
            {
                "description": (
                    "Retained launch, patch, and source-hash provenance for the July "
                    "campaign. Published copies replace local absolute paths only; "
                    "original hashes identify the private source files."
                ),
                "files": provenance,
            },
            indent=2,
        )
        + "\n"
    )
    print(
        f"Wrote {len(runs)} canonical runs and {len(inventory['attempts'])} attempts to {OUT_DIR}"
    )


if __name__ == "__main__":
    main()
