#!/usr/bin/env python3
"""Regenerate the July 2026 full-coverage Claude tables.

Default input is the tracked canonical manifest
(`planning/claude28/claude28_canonical_manifest.json`). With
`--evidence-dir`, evaluator fields and trace indicators are instead read from
packaged run artifacts (`runs/claude_native_28/<run_id>/`) and must match the
manifest before any table is written.

Estimand: per task, average five trials within each model/condition cell,
average the two models, then take with-skill minus no-skill. Intervals are
95% percentile task bootstraps (20,000 draws, seed 20260504). Strict pass and
key F1 are reported separately from reward.

Sensitivity subsets drop tasks whose no-skill and with-skill cells differ in
recorded harness indicators (Claude Code version observed in traces, and
whether model-slot overrides were recorded). They match recorded indicators,
not every realized ancillary model call.

Stdlib only, so it runs from a clean checkout without the M4 environment.
"""

from __future__ import annotations

import argparse
import difflib
import json
import math
import os
import random
import statistics
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

PAPER_DIR = Path(
    os.environ.get("M4BENCH_PAPER_DIR", Path(__file__).resolve().parents[1])
).resolve()
MANIFEST = PAPER_DIR / "planning" / "claude28" / "claude28_canonical_manifest.json"
TASK_DETAILS = PAPER_DIR / "tables" / "task_details.tex"
MODELS = ("opus", "sonnet")
CONDITIONS = ("no-skill", "with-skill")
BOOTSTRAP_DRAWS = 20000
BOOTSTRAP_SEED = 20260504
EVIDENCE_CAMPAIGN = "claude_native_28"
OUTPUTS = {
    "effect": Path("tables/claude28_native_skill_effect.tex"),
    "tasks": Path("tables/claude28_task_deltas.tex"),
    "sensitivity": Path("tables/claude28_harness_sensitivity.tex"),
    "harness": Path("tables/claude28_harness_profile.tex"),
    "summary": Path("planning/claude28/claude28_results_summary.json"),
}


def latex_escape(value: object) -> str:
    replacements = {"&": r"\&", "%": r"\%", "_": r"\_", "#": r"\#", "$": r"\$"}
    return "".join(replacements.get(ch, ch) for ch in str(value))


def fmt(value: float, digits: int = 3) -> str:
    return f"{value:.{digits}f}"


def fmt_ci(value: float, interval: list[float]) -> str:
    return f"{fmt(value)} [{fmt(interval[0])}, {fmt(interval[1])}]"


def tabular(headers: list[str], rows: list[list[object]], align: str) -> str:
    lines = [rf"\begin{{tabular}}{{{align}}}", r"\toprule"]
    lines.append(" & ".join(latex_escape(h) for h in headers) + r" \\")
    lines.append(r"\midrule")
    lines += [" & ".join(latex_escape(c) for c in row) + r" \\" for row in rows]
    lines += [r"\bottomrule", r"\end{tabular}", ""]
    return "\n".join(lines)


def bootstrap_ci(values: list[float]) -> list[float]:
    rng = random.Random(BOOTSTRAP_SEED)
    n = len(values)
    draws = sorted(
        statistics.mean(values[rng.randrange(n)] for _ in range(n))
        for _ in range(BOOTSTRAP_DRAWS)
    )
    return [draws[int(0.025 * BOOTSTRAP_DRAWS)], draws[int(0.975 * BOOTSTRAP_DRAWS)]]


def reference_rows() -> dict[str, int]:
    rows = {}
    for line in TASK_DETAILS.read_text().splitlines():
        fields = [part.strip().removesuffix(r"\\").strip() for part in line.split("&")]
        if len(fields) == 6 and fields[5].isdigit():
            rows[fields[0]] = int(fields[5])
    return rows


def trace_indicators(trace_text: str) -> dict[str, list[str]]:
    """Recorded model/version indicators, using the audit's trace rules."""
    models, usage, versions = set(), set(), set()
    for line in trace_text.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue  # wrapper log lines are plain text
        if not isinstance(event, dict):
            continue
        message = event.get("message")
        if event.get("type") == "assistant" and isinstance(message, dict):
            if isinstance(message.get("model"), str):
                models.add(message["model"])
        if isinstance(event.get("modelUsage"), dict):
            usage.update(event["modelUsage"])
        if event.get("type") == "system":
            for key in ("claude_code_version", "version"):
                if isinstance(event.get(key), str):
                    versions.add(event[key])
    return {
        "assistant_models": sorted(models),
        "usage_models": sorted(usage),
        "cli_versions": sorted(versions),
    }


def analysis_record(run: dict[str, Any]) -> dict[str, Any]:
    tests = run["test_results"]
    return {
        "run_id": run["run_id"],
        "task": run["task"],
        "model": run["model_alias"],
        "condition": run["condition"],
        "trial": run["trial"],
        "reward": tests["reward"],
        "strict_pass": tests["failed"] == 0 and tests["errors"] == 0,
        "agent_unique_keys": tests["agent_unique_keys"],
        "extra_keys": tests["extra_keys"],
        "key_precision": tests["key_precision"],
        "cli_versions": tuple(run["trace_observed"]["cli_versions"]),
        "model_overrides": bool(run["recorded_model_overrides"]),
        "haiku_usage": any("haiku" in m for m in run["trace_observed"]["usage_models"]),
        "haiku_assistant": any(
            "haiku" in m for m in run["trace_observed"]["assistant_models"]
        ),
        "elapsed_seconds": run["agent_elapsed_seconds"],
        "token_usage": run["token_usage"],
    }


def evidence_records(evidence_dir: Path, manifest_runs: list[dict]) -> list[dict]:
    """Rebuild analysis records from packaged artifacts and cross-check them."""
    records = []
    mismatches = []
    compared = [
        "reward",
        "failed",
        "errors",
        "agent_unique_keys",
        "extra_keys",
        "key_precision",
    ]
    for run in manifest_runs:
        run_dir = evidence_dir / "runs" / EVIDENCE_CAMPAIGN / run["run_id"]
        result = json.loads((run_dir / "result.json").read_text())
        trace = trace_indicators((run_dir / "trace.jsonl").read_text(errors="replace"))
        tests = result["test_results"]
        for key in compared:
            if tests.get(key) != run["test_results"][key]:
                mismatches.append(f"{run['run_id']}: {key}")
        if trace["cli_versions"] != run["trace_observed"]["cli_versions"]:
            mismatches.append(f"{run['run_id']}: cli_versions")
        if trace["assistant_models"] != run["trace_observed"]["assistant_models"]:
            mismatches.append(f"{run['run_id']}: assistant_models")
        overrides = result.get("claude_model_overrides")
        if bool(overrides) != bool(run["recorded_model_overrides"]):
            mismatches.append(f"{run['run_id']}: recorded_model_overrides")
        elapsed = (result.get("agent_result") or {}).get("elapsed_seconds")
        usage = result.get("token_usage") or {}
        token_usage = {key: usage.get(key) for key in run["token_usage"]}
        if elapsed != run["agent_elapsed_seconds"] or token_usage != run["token_usage"]:
            mismatches.append(f"{run['run_id']}: elapsed/token usage")
        records.append(
            analysis_record(
                {
                    **run,
                    "test_results": {
                        key: tests.get(key) for key in run["test_results"]
                    },
                    "trace_observed": trace,
                    "recorded_model_overrides": overrides,
                    "agent_elapsed_seconds": elapsed,
                    "token_usage": token_usage,
                }
            )
        )
    if mismatches:
        raise SystemExit(
            f"{len(mismatches)} evidence/manifest mismatches:\n  "
            + "\n  ".join(mismatches[:20])
        )
    return records


def task_rows(records: list[dict], ref_rows: dict[str, int]) -> list[dict]:
    cells: dict[tuple, list[dict]] = defaultdict(list)
    for record in records:
        cells[(record["task"], record["model"], record["condition"])].append(record)
    rows = []
    for task in sorted({record["task"] for record in records}):
        row: dict[str, Any] = {"task": task, "cells": {}}
        for model in MODELS:
            for condition in CONDITIONS:
                runs = cells[(task, model, condition)]
                if sorted(r["trial"] for r in runs) != [1, 2, 3, 4, 5]:
                    raise SystemExit(f"{task}/{model}/{condition}: expected trials 1-5")
                n_ref = ref_rows[task]
                key_f1 = [
                    2
                    * (r["agent_unique_keys"] - r["extra_keys"])
                    / (r["agent_unique_keys"] + n_ref)
                    for r in runs
                ]
                row["cells"][f"{model}/{condition}"] = {
                    "reward": statistics.mean(r["reward"] for r in runs),
                    "key_f1": statistics.mean(key_f1),
                    "strict_passes": sum(r["strict_pass"] for r in runs),
                    "harness_profiles": dict(
                        Counter(
                            f"{','.join(r['cli_versions'])}|"
                            f"{'overrides' if r['model_overrides'] else 'native-routing'}"
                            for r in runs
                        )
                    ),
                    "cli_versions": dict(
                        Counter(",".join(r["cli_versions"]) for r in runs)
                    ),
                }
        c = row["cells"]
        row["cli_matched"] = all(
            c[f"{m}/no-skill"]["cli_versions"] == c[f"{m}/with-skill"]["cli_versions"]
            and len(c[f"{m}/no-skill"]["cli_versions"]) == 1
            for m in MODELS
        )
        row["cli_and_routing_matched"] = all(
            c[f"{m}/no-skill"]["harness_profiles"]
            == c[f"{m}/with-skill"]["harness_profiles"]
            and len(c[f"{m}/no-skill"]["harness_profiles"]) == 1
            for m in MODELS
        )
        for model in MODELS:
            row[f"{model}_delta"] = (
                c[f"{model}/with-skill"]["reward"] - c[f"{model}/no-skill"]["reward"]
            )
        row["no_skill"] = statistics.mean(c[f"{m}/no-skill"]["reward"] for m in MODELS)
        row["with_skill"] = statistics.mean(
            c[f"{m}/with-skill"]["reward"] for m in MODELS
        )
        row["delta"] = row["with_skill"] - row["no_skill"]
        rows.append(row)
    return rows


def summarize(rows: list[dict]) -> dict[str, Any]:
    deltas = [row["delta"] for row in rows]
    summary: dict[str, Any] = {
        "tasks": len(rows),
        "runs": 20 * len(rows),
        "no_skill": statistics.mean(row["no_skill"] for row in rows),
        "with_skill": statistics.mean(row["with_skill"] for row in rows),
        "delta": statistics.mean(deltas),
        "delta_ci95": bootstrap_ci(deltas),
        "positive_tasks": sum(value > 0 for value in deltas),
    }
    for model in MODELS:
        model_deltas = [row[f"{model}_delta"] for row in rows]
        summary[model] = {
            "no_skill": statistics.mean(
                row["cells"][f"{model}/no-skill"]["reward"] for row in rows
            ),
            "with_skill": statistics.mean(
                row["cells"][f"{model}/with-skill"]["reward"] for row in rows
            ),
            "delta": statistics.mean(model_deltas),
            "delta_ci95": bootstrap_ci(model_deltas),
            "positive_tasks": sum(value > 0 for value in model_deltas),
        }
    for condition in CONDITIONS:
        summary[f"strict_passes/{condition}"] = sum(
            row["cells"][f"{m}/{condition}"]["strict_passes"]
            for row in rows
            for m in MODELS
        )
        summary[f"key_f1/{condition}"] = statistics.mean(
            statistics.mean(row["cells"][f"{m}/{condition}"]["key_f1"] for m in MODELS)
            for row in rows
        )
    summary["key_f1/delta"] = summary["key_f1/with-skill"] - summary["key_f1/no-skill"]
    return summary


def render(records: list[dict], ref_rows: dict[str, int]) -> dict[Path, str]:
    rows = task_rows(records, ref_rows)
    subsets = {
        "all_tasks": rows,
        "cli_matched": [row for row in rows if row["cli_matched"]],
        "cli_and_routing_matched": [
            row for row in rows if row["cli_and_routing_matched"]
        ],
    }
    summaries = {name: summarize(subset) for name, subset in subsets.items()}
    full = summaries["all_tasks"]

    effect_rows = [
        [
            f"Claude {model.capitalize()}",
            fmt(full[model]["no_skill"]),
            fmt(full[model]["with_skill"]),
            fmt_ci(full[model]["delta"], full[model]["delta_ci95"]),
            f"{full[model]['positive_tasks']}/{full['tasks']}",
        ]
        for model in MODELS
    ]
    effect_rows.append(
        [
            "Task-balanced mean",
            fmt(full["no_skill"]),
            fmt(full["with_skill"]),
            fmt_ci(full["delta"], full["delta_ci95"]),
            f"{full['positive_tasks']}/{full['tasks']}",
        ]
    )
    effect = tabular(
        ["Model", "No skill", "With skill", "Task-paired delta", "Positive tasks"],
        effect_rows,
        "lrrrr",
    )

    labels = {
        "all_tasks": "All tasks",
        "cli_matched": "CLI-version matched",
        "cli_and_routing_matched": "CLI and routing matched",
    }
    sensitivity = tabular(
        [
            "Task set",
            "Tasks",
            "Runs",
            "Delta [95% CI]",
            "Positive",
            "Strict passes (no/with)",
            "Key F1 delta",
        ],
        [
            [
                labels[name],
                s["tasks"],
                s["runs"],
                fmt_ci(s["delta"], s["delta_ci95"]),
                f"{s['positive_tasks']}/{s['tasks']}",
                f"{s['strict_passes/no-skill']}/{s['runs'] // 2} vs {s['strict_passes/with-skill']}/{s['runs'] // 2}",
                fmt(s["key_f1/delta"]),
            ]
            for name, s in summaries.items()
        ],
        "lrrrrrr",
    )

    def harness_flag(row: dict) -> str:
        if row["cli_and_routing_matched"]:
            return "matched"
        return "CLI" if not row["cli_matched"] else "routing"

    tasks = tabular(
        ["Task", "Opus delta", "Sonnet delta", "Mean delta", "Harness"],
        [
            [
                row["task"],
                fmt(row["opus_delta"]),
                fmt(row["sonnet_delta"]),
                fmt(row["delta"]),
                harness_flag(row),
            ]
            for row in sorted(rows, key=lambda item: item["delta"], reverse=True)
        ],
        "lrrrl",
    )

    profile_rows = []
    profiles = {}
    for condition in CONDITIONS:
        subset = [r for r in records if r["condition"] == condition]
        versions = Counter(",".join(r["cli_versions"]) for r in subset)
        profile = {
            "runs": len(subset),
            "cli_versions": dict(sorted(versions.items())),
            "recorded_model_overrides": sum(r["model_overrides"] for r in subset),
            "haiku_in_usage": sum(r["haiku_usage"] for r in subset),
            "haiku_assistant_turns": sum(r["haiku_assistant"] for r in subset),
            # fsum: built-in sum() rounds float totals differently before Python 3.12.
            "agent_hours": math.fsum(r["elapsed_seconds"] or 0 for r in subset) / 3600,
            "input_tokens": sum(
                (r["token_usage"]["input_tokens"] or 0) for r in subset
            ),
            "cached_input_tokens": sum(
                (r["token_usage"]["cached_input_tokens"] or 0) for r in subset
            ),
            "output_tokens": sum(
                (r["token_usage"]["output_tokens"] or 0) for r in subset
            ),
        }
        profiles[condition] = profile
        profile_rows.append(
            [
                condition,
                profile["runs"],
                versions.get("2.1.119", 0),
                versions.get("2.1.220", 0),
                profile["recorded_model_overrides"],
                profile["haiku_in_usage"],
                profile["haiku_assistant_turns"],
                f"{profile['agent_hours']:.1f}",
            ]
        )
    if set(Counter(",".join(r["cli_versions"]) for r in records)) - {
        "2.1.119",
        "2.1.220",
    }:
        raise SystemExit(
            "Unexpected Claude Code versions; extend the harness profile table"
        )
    harness = tabular(
        [
            "Condition",
            "Runs",
            "CLI 2.1.119",
            "CLI 2.1.220",
            "Overrides recorded",
            "Haiku usage",
            "Haiku turns",
            "Agent hours",
        ],
        profile_rows,
        "lrrrrrrr",
    )

    summary_json = {
        "description": "Generated by make_claude28_tables.py from the canonical 560-run manifest.",
        "bootstrap": {
            "draws": BOOTSTRAP_DRAWS,
            "seed": BOOTSTRAP_SEED,
            "unit": "task",
            "interval": "percentile 95%",
        },
        "summaries": summaries,
        "harness_profile_by_condition": profiles,
        "excluded_from_cli_matched": [r["task"] for r in rows if not r["cli_matched"]],
        "excluded_from_cli_and_routing_matched": [
            r["task"] for r in rows if not r["cli_and_routing_matched"]
        ],
        "tasks": rows,
    }
    return {
        OUTPUTS["effect"]: effect,
        OUTPUTS["sensitivity"]: sensitivity,
        OUTPUTS["tasks"]: tasks,
        OUTPUTS["harness"]: harness,
        OUTPUTS["summary"]: json.dumps(summary_json, indent=2) + "\n",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        help="Extracted camera-ready evidence package; read run artifacts instead of manifest fields.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not write; exit non-zero if regenerated outputs differ from tracked files.",
    )
    args = parser.parse_args()

    manifest = json.loads(MANIFEST.read_text())
    ref_rows = reference_rows()
    if args.evidence_dir:
        records = evidence_records(args.evidence_dir, manifest["runs"])
    else:
        records = [analysis_record(run) for run in manifest["runs"]]
    if len(records) != 560:
        raise SystemExit(f"Expected 560 canonical runs, found {len(records)}")
    outputs = render(records, ref_rows)

    if args.check:
        differing = []
        for relative, text in outputs.items():
            tracked = PAPER_DIR / relative
            current = tracked.read_text() if tracked.exists() else ""
            if current != text:
                differing.append(str(relative))
                sys.stdout.writelines(
                    difflib.unified_diff(
                        current.splitlines(True),
                        text.splitlines(True),
                        str(tracked),
                        "regenerated",
                        n=1,
                    )
                )
        if differing:
            raise SystemExit(f"Regenerated outputs differ: {', '.join(differing)}")
        print(f"All {len(outputs)} Claude 28-task outputs match ({len(records)} runs).")
        return

    for relative, text in outputs.items():
        path = PAPER_DIR / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as handle:
            handle.write(text)
        Path(handle.name).replace(path)
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
