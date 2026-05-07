#!/usr/bin/env python3
"""Generate manuscript tables for the May 6 validity follow-up."""

from __future__ import annotations

import json
import os
import random
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

M4_DIR = Path(
    os.environ.get("M4BENCH_M4_DIR", Path(__file__).resolve().parents[4])
).resolve()
PAPER_DIR = Path(
    os.environ.get("M4BENCH_PAPER_DIR", Path(__file__).resolve().parents[1])
).resolve()
BENCHMARK_DIR = M4_DIR / "benchmark"
RESULTS_DIR = Path(
    os.environ.get("M4BENCH_RESULTS_DIR", BENCHMARK_DIR / "results")
).resolve()
TABLE_DIR = PAPER_DIR / "tables"
PLANNING_DIR = PAPER_DIR / "planning"

FOLLOWUP_ROOT = RESULTS_DIR / "codex-validity-followup-20260506"
SCHEMA_NO_SKILL_ROOT = RESULTS_DIR / "codex-full-20260428"
FOLLOWUP_MANIFEST = PLANNING_DIR / "followup_canonical_manifest.json"

SENTINEL_TASKS = [
    "mimic-urine-output-rate-raw",
    "mimic-ventilation",
    "mimic-creatinine-baseline-raw",
    "mimic-suspicion-infection",
    "mimic-vasopressor-equivalents-raw",
    "mimic-oasis-24h",
    "mimic-sepsis3-raw",
    "mimic-sofa-24h-raw",
]


sys.path.insert(0, str(BENCHMARK_DIR))
from report_results import cell_rows, load_rows, mean  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_final_results import (  # noqa: E402
    CODEX_RELEASE,
    CODEX_RERUN,
    bootstrap_ci,
    combine_rows,
    fmt,
    write_table,
)


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


def with_neutral_tier(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for row in rows:
        row.setdefault("tier", "")
        row.setdefault("tier_name", "")
    return rows


def canonicalize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str, str, str, int], dict[str, Any]] = {}
    for row in rows:
        key = run_key(row)
        if key not in by_key or timestamp_key(row) > timestamp_key(by_key[key]):
            by_key[key] = row
    return with_neutral_tier(list(by_key.values()))


def load_followup_rows_from_manifest() -> list[dict[str, Any]]:
    if not FOLLOWUP_MANIFEST.exists():
        return canonicalize(load_rows(FOLLOWUP_ROOT))

    manifest = json.loads(FOLLOWUP_MANIFEST.read_text())
    rows = []
    for record in manifest["canonical_runs"]:
        run_dir = RESULTS_DIR / record["relative_run_dir"]
        data = json.loads((run_dir / "result.json").read_text())
        test = data.get("test_results") or {}
        agent = data.get("agent_result") or {}
        canary = data.get("filesystem_canary") or {}
        lint = data.get("contamination_lint") or {}
        rows.append(
            {
                "run_id": data.get("run_id", run_dir.name),
                "path": str(run_dir),
                "task": data.get("task"),
                "condition": data.get("condition"),
                "schema": data.get("schema", "native"),
                "agent": data.get("agent"),
                "model": data.get("model"),
                "trial": data.get("trial"),
                "publishable": bool(data.get("publishable")),
                "isolated": bool(data.get("isolated")),
                "filesystem_canary": bool(canary.get("passed")),
                "contamination_lint": bool(lint.get("passed")),
                "agent_returncode": agent.get("returncode", agent.get("exit_code")),
                "passed": test.get("passed"),
                "failed": test.get("failed"),
                "errors": test.get("errors"),
                "reward": test.get("reward"),
                "diagnostics_failed": bool(test.get("diagnostics_failed")),
                "key_precision": test.get("key_precision"),
                "extra_keys": test.get("extra_keys"),
            }
        )
    return with_neutral_tier(rows)


def cells_index(
    rows: list[dict[str, Any]],
) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    return {
        (row["task"], row["condition"], row["schema"], row["model"]): row
        for row in cell_rows(with_neutral_tier(rows))
    }


def task_bootstrap(values: list[float]) -> tuple[float, float]:
    return bootstrap_ci(values, reps=20000, seed=20260506)


def sign_flip_p(values: list[float], reps: int = 200000, seed: int = 20260506) -> float:
    observed = abs(mean(values))
    rng = random.Random(seed)
    hits = 0
    for _ in range(reps):
        flipped = [value if rng.randrange(2) else -value for value in values]
        if abs(mean(flipped)) >= observed:
            hits += 1
    return (hits + 1) / (reps + 1)


def write_operational_spec_tables(base_idx: dict, follow_idx: dict) -> dict[str, Any]:
    per_task = []
    per_model_rows = []
    for task in SENTINEL_TASKS:
        model_records = []
        for model in ("gpt-5.4-mini", "gpt-5.5"):
            no_skill = base_idx[(task, "no-skill", "native", model)]["mean_reward"]
            targeted = base_idx[(task, "with-skill", "native", model)]["mean_reward"]
            spec = follow_idx[(task, "operational-spec", "native", model)][
                "mean_reward"
            ]
            model_records.append((no_skill, spec, targeted))
            per_model_rows.append(
                [
                    task,
                    model,
                    fmt(no_skill),
                    fmt(spec),
                    fmt(targeted),
                    fmt(spec - no_skill),
                    fmt(targeted - spec),
                ]
            )
        no_mean = mean(record[0] for record in model_records)
        spec_mean = mean(record[1] for record in model_records)
        targeted_mean = mean(record[2] for record in model_records)
        per_task.append(
            {
                "task": task,
                "no_skill": no_mean,
                "operational_spec": spec_mean,
                "targeted": targeted_mean,
                "spec_minus_no": spec_mean - no_mean,
                "targeted_minus_spec": targeted_mean - spec_mean,
            }
        )

    spec_no_values = [row["spec_minus_no"] for row in per_task]
    target_spec_values = [row["targeted_minus_spec"] for row in per_task]
    spec_no_ci = task_bootstrap(spec_no_values)
    target_spec_ci = task_bootstrap(target_spec_values)

    write_table(
        TABLE_DIR / "codex_operational_spec_control.tex",
        [
            "Comparison",
            "Tasks",
            "No skill",
            "Operational spec",
            "Targeted skill",
            "Delta",
        ],
        [
            [
                "Operational spec--no skill",
                len(per_task),
                fmt(mean(row["no_skill"] for row in per_task)),
                fmt(mean(row["operational_spec"] for row in per_task)),
                "--",
                f"{fmt(mean(spec_no_values))} [{fmt(spec_no_ci[0])}, {fmt(spec_no_ci[1])}]",
            ],
            [
                "Targeted skill--operational spec",
                len(per_task),
                "--",
                fmt(mean(row["operational_spec"] for row in per_task)),
                fmt(mean(row["targeted"] for row in per_task)),
                f"{fmt(mean(target_spec_values))} [{fmt(target_spec_ci[0])}, {fmt(target_spec_ci[1])}]",
            ],
        ],
        "lrrrrr",
    )

    write_table(
        TABLE_DIR / "codex_operational_spec_by_task.tex",
        [
            "Task",
            "No skill",
            "Operational spec",
            "Targeted skill",
            "Spec--no",
            "Targeted--spec",
        ],
        [
            [
                row["task"],
                fmt(row["no_skill"]),
                fmt(row["operational_spec"]),
                fmt(row["targeted"]),
                fmt(row["spec_minus_no"]),
                fmt(row["targeted_minus_spec"]),
            ]
            for row in per_task
        ],
        "lrrrrr",
    )

    return {
        "tasks": len(per_task),
        "spec_minus_no": mean(spec_no_values),
        "spec_minus_no_ci": spec_no_ci,
        "spec_minus_no_positive": sum(value > 0 for value in spec_no_values),
        "targeted_minus_spec": mean(target_spec_values),
        "targeted_minus_spec_ci": target_spec_ci,
        "targeted_minus_spec_positive": sum(value > 0 for value in target_spec_values),
        "targeted_minus_spec_p": sign_flip_p(target_spec_values),
        "spec_no_p": sign_flip_p(spec_no_values),
    }


def write_schema_tables(
    base_idx: dict, follow_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    no_skill_rows = [
        row
        for row in canonicalize(load_rows(SCHEMA_NO_SKILL_ROOT))
        if row["condition"] == "no-skill"
        and row["schema"] in {"obfuscated", "restructured"}
        and row["model"] == "gpt-5.4-mini"
    ]
    with_skill_rows = [
        row
        for row in follow_rows
        if row["condition"] == "with-skill"
        and row["schema"] in {"obfuscated", "restructured"}
        and row["model"] == "gpt-5.4-mini"
    ]
    schema_idx = cells_index(with_neutral_tier(no_skill_rows + with_skill_rows))
    schema_tasks = sorted(
        {row["task"] for row in no_skill_rows}
        & {row["task"] for row in with_skill_rows}
    )

    schema_summaries = []
    for schema in ("native", "obfuscated", "restructured"):
        no_values = []
        with_values = []
        deltas = []
        for task in schema_tasks:
            if schema == "native":
                no_cell = base_idx[(task, "no-skill", "native", "gpt-5.4-mini")]
                with_cell = base_idx[(task, "with-skill", "native", "gpt-5.4-mini")]
            else:
                no_cell = schema_idx[(task, "no-skill", schema, "gpt-5.4-mini")]
                with_cell = schema_idx[(task, "with-skill", schema, "gpt-5.4-mini")]
            no_reward = no_cell["mean_reward"]
            with_reward = with_cell["mean_reward"]
            no_values.append(no_reward)
            with_values.append(with_reward)
            deltas.append(with_reward - no_reward)
        ci_low, ci_high = task_bootstrap(deltas)
        schema_summaries.append(
            {
                "schema": schema,
                "tasks": len(deltas),
                "no_skill": mean(no_values),
                "with_skill": mean(with_values),
                "delta": mean(deltas),
                "ci": (ci_low, ci_high),
                "positive": sum(value > 0 for value in deltas),
            }
        )

    native_delta = next(
        row["delta"] for row in schema_summaries if row["schema"] == "native"
    )
    write_table(
        TABLE_DIR / "codex_schema_skill_generalization.tex",
        [
            "Schema",
            "Tasks",
            "No skill",
            "With skill",
            "Skill delta",
            "Positive tasks",
            "Robustness ratio",
        ],
        [
            [
                row["schema"],
                row["tasks"],
                fmt(row["no_skill"]),
                fmt(row["with_skill"]),
                f"{fmt(row['delta'])} [{fmt(row['ci'][0])}, {fmt(row['ci'][1])}]",
                f"{row['positive']}/{row['tasks']}",
                fmt(row["delta"] / native_delta) if native_delta else "NA",
            ]
            for row in schema_summaries
        ],
        "lrrrrrr",
    )

    return {
        "tasks": len(schema_tasks),
        "summaries": schema_summaries,
    }


def write_followup_integrity_table(follow_rows: list[dict[str, Any]]) -> None:
    raw_count = len(load_rows(FOLLOWUP_ROOT))
    canonical_count = len(follow_rows)
    condition_counts = Counter(
        (row["condition"], row["schema"], row["model"]) for row in follow_rows
    )
    rows = [
        ["Raw result directories", raw_count],
        ["Canonical run keys", canonical_count],
        ["Superseded duplicate directories", raw_count - canonical_count],
        [
            "Operational-spec canonical runs",
            sum(row["condition"] == "operational-spec" for row in follow_rows),
        ],
        [
            "Transformed-schema with-skill canonical runs",
            sum(
                row["condition"] == "with-skill" and row["schema"] != "native"
                for row in follow_rows
            ),
        ],
        [
            "Publishable flag failures",
            sum(not row["publishable"] for row in follow_rows),
        ],
        ["Isolation flag failures", sum(not row["isolated"] for row in follow_rows)],
        [
            "Filesystem canary failures",
            sum(not row["filesystem_canary"] for row in follow_rows),
        ],
        [
            "Contamination-lint failures",
            sum(not row["contamination_lint"] for row in follow_rows),
        ],
        [
            "Nonzero agent exits",
            sum(row["agent_returncode"] not in (0, None, "") for row in follow_rows),
        ],
        [
            "Fully passing diagnostic runs",
            sum(
                (row["failed"] or 0) == 0 and (row["errors"] or 0) == 0
                for row in follow_rows
            ),
        ],
    ]
    for (condition, schema, model), count in sorted(condition_counts.items()):
        rows.append([f"{condition} / {schema} / {model}", count])
    write_table(
        TABLE_DIR / "codex_followup_integrity.tex",
        ["Audit quantity", "Count"],
        rows,
        "lr",
    )


def write_summary(ops: dict[str, Any], schema: dict[str, Any]) -> None:
    schema_lines = []
    for row in schema["summaries"]:
        schema_lines.append(
            f"- {row['schema']}: {fmt(row['delta'])} [{fmt(row['ci'][0])}, {fmt(row['ci'][1])}], {row['positive']}/{row['tasks']} positive tasks."
        )
    lines = [
        "# Follow-up Result Summary",
        "",
        "Generated by `benchmark/release/v1/scripts/make_followup_tables.py` using the canonical May 6 follow-up manifest.",
        "",
        "## Operational-spec control",
        "",
        f"- Operational spec minus no skill: {fmt(ops['spec_minus_no'])} [{fmt(ops['spec_minus_no_ci'][0])}, {fmt(ops['spec_minus_no_ci'][1])}], positive on {ops['spec_minus_no_positive']}/{ops['tasks']} tasks.",
        f"- Targeted skill minus operational spec: {fmt(ops['targeted_minus_spec'])} [{fmt(ops['targeted_minus_spec_ci'][0])}, {fmt(ops['targeted_minus_spec_ci'][1])}], positive on {ops['targeted_minus_spec_positive']}/{ops['tasks']} tasks.",
        "",
        "## Schema-skill generalization",
        "",
        *schema_lines,
        "",
    ]
    (PLANNING_DIR / "followup_results_summary.md").write_text("\n".join(lines))


def main() -> None:
    TABLE_DIR.mkdir(exist_ok=True)
    PLANNING_DIR.mkdir(exist_ok=True)
    follow_rows = load_followup_rows_from_manifest()
    base_rows, _ = combine_rows(CODEX_RELEASE, CODEX_RERUN)
    base_idx = cells_index(with_neutral_tier(base_rows))
    follow_idx = cells_index(follow_rows)

    ops_summary = write_operational_spec_tables(base_idx, follow_idx)
    schema_summary = write_schema_tables(base_idx, follow_rows)
    write_followup_integrity_table(follow_rows)
    write_summary(ops_summary, schema_summary)
    print("Wrote follow-up result tables and summary.")


if __name__ == "__main__":
    main()
