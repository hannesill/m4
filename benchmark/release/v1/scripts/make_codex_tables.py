#!/usr/bin/env python3
"""Generate manuscript tables for the current Codex release campaign."""

from __future__ import annotations

import csv
import math
import os
import statistics
from collections import defaultdict
from pathlib import Path

import tomllib

M4_DIR = Path(
    os.environ.get("M4BENCH_M4_DIR", Path(__file__).resolve().parents[4])
).resolve()
PAPER_DIR = Path(
    os.environ.get("M4BENCH_PAPER_DIR", M4_DIR.parent / "m4bench-paper")
).resolve()
BENCHMARK_DIR = M4_DIR / "benchmark"
TASK_DIR = BENCHMARK_DIR / "tasks"
RESULT_ROOT = Path(
    os.environ.get(
        "M4BENCH_PAPER_ROOT", BENCHMARK_DIR / "results" / "release-20260502-codex-v11"
    )
).resolve()
ANALYSIS_DIR = RESULT_ROOT / "analysis"
TABLE_DIR = PAPER_DIR / "tables"


def latex_escape(value: object) -> str:
    text = str(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(ch, ch) for ch in text)


def fmt(value: float | int | str, digits: int = 3) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value)
    if math.isnan(value):
        return "NA"
    return f"{value:.{digits}f}"


def write_table(
    path: Path, headers: list[str], rows: list[list[object]], align: str
) -> None:
    lines = [rf"\begin{{tabular}}{{{align}}}", r"\toprule"]
    lines.append(" & ".join(latex_escape(h) for h in headers) + r" \\")
    lines.append(r"\midrule")
    for row in rows:
        lines.append(" & ".join(latex_escape(cell) for cell in row) + r" \\")
    lines.extend([r"\bottomrule", r"\end{tabular}", ""])
    path.write_text("\n".join(lines))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def as_float(row: dict[str, str], key: str) -> float:
    return float(row[key])


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else float("nan")


def generate_task_inventory() -> None:
    family_counts: dict[str, defaultdict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    for task_file in sorted(TASK_DIR.glob("*/*/task.toml")):
        family = task_file.parents[1].name
        with task_file.open("rb") as handle:
            config = tomllib.load(handle)
        mode = config.get("metadata", {}).get("mode", "standard")
        database = config.get("metadata", {}).get("database", "unknown")
        family_counts[family]["tasks"] += 1
        family_counts[family][mode] += 1
        family_counts[family][database] += 1

    rows = []
    for family, counts in sorted(family_counts.items()):
        dbs = []
        for db_name in ("mimic-iv", "eicu"):
            if counts[db_name]:
                dbs.append(f"{db_name} ({counts[db_name]})")
        rows.append(
            [
                family,
                counts["tasks"],
                counts["standard"],
                counts["raw"],
                ", ".join(dbs),
            ]
        )

    write_table(
        TABLE_DIR / "task_inventory.tex",
        ["Family", "Tasks", "Standard", "Raw", "Database"],
        rows,
        align="lrrrr",
    )


def _ground_truth_rows(task_name: str, config: dict) -> int | str:
    alias = config.get("ground_truth", {}).get("alias")
    task_key = alias or task_name.replace("mimic-", "").replace("eicu-", "")
    for suffix in (".csv", ".csv.gz"):
        path = BENCHMARK_DIR / "ground_truth" / f"{task_key}{suffix}"
        if not path.exists():
            continue
        import gzip

        opener = gzip.open if suffix.endswith(".gz") else open
        with opener(path, "rt") as handle:
            return sum(1 for _ in handle) - 1
    return "NA"


def generate_task_details() -> None:
    rows = []
    for task_file in sorted(TASK_DIR.glob("*/*/task.toml")):
        with task_file.open("rb") as handle:
            config = tomllib.load(handle)
        metadata = config["metadata"]
        evaluation = config["evaluation"]
        rows.append(
            [
                metadata["name"],
                metadata.get("mode", "standard"),
                metadata.get("database", "unknown"),
                ", ".join(evaluation["key_columns"]),
                len(evaluation["value_columns"]),
                _ground_truth_rows(metadata["name"], config),
            ]
        )

    write_table(
        TABLE_DIR / "task_details.tex",
        ["Task", "Mode", "Database", "Key grain", "Scored columns", "Truth rows"],
        rows,
        align="llllrr",
    )


def generate_integrity_table(
    runs: list[dict[str, str]], cells: list[dict[str, str]]
) -> None:
    full_pass = sum(int(r["failed"]) == 0 and int(r["errors"]) == 0 for r in runs)
    diagnostics_failed = sum(r["diagnostics_failed"] == "True" for r in runs)
    rows = [
        ["Runs", len(runs)],
        ["Expected primary/supplementary runs", "lock from final matrix"],
        ["Task/condition/schema/model cells", len(cells)],
        ["Publishable flag failures", sum(r["publishable"] != "True" for r in runs)],
        ["Isolation flag failures", sum(r["isolated"] != "True" for r in runs)],
        [
            "Filesystem canary failures",
            sum(r["filesystem_canary"] != "True" for r in runs),
        ],
        [
            "Contamination-lint failures",
            sum(r["contamination_lint"] != "True" for r in runs),
        ],
        [
            "Nonzero agent exits",
            sum(r["agent_returncode"] not in {"0", ""} for r in runs),
        ],
        ["Missing rewards", sum(r["reward"] == "" for r in runs)],
        ["Fully passing diagnostic runs", full_pass],
        ["Runs with semantic diagnostic failures", diagnostics_failed],
    ]
    write_table(
        TABLE_DIR / "codex_integrity.tex",
        ["Audit quantity", "Count"],
        rows,
        align="lr",
    )


def generate_native_skill_summary(
    runs: list[dict[str, str]], deltas: list[dict[str, str]]
) -> None:
    reward_groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    for run in runs:
        if run["schema"] == "native" and run["condition"] in {"no-skill", "with-skill"}:
            reward_groups[(run["model"], run["condition"])].append(
                as_float(run, "reward")
            )

    delta_groups: dict[str, list[float]] = defaultdict(list)
    for row in deltas:
        delta_groups[row["model"]].append(as_float(row, "delta"))

    rows: list[list[object]] = []
    for model in ("gpt-5.4-mini", "gpt-5.5"):
        model_deltas = delta_groups[model]
        rows.append(
            [
                model,
                fmt(mean(reward_groups[(model, "no-skill")])),
                fmt(mean(reward_groups[(model, "with-skill")])),
                fmt(mean(model_deltas)),
                f"{sum(d > 0 for d in model_deltas)}/{len(model_deltas)}",
            ]
        )

    by_task: dict[str, list[float]] = defaultdict(list)
    for row in deltas:
        by_task[row["task"]].append(as_float(row, "delta"))
    task_deltas = [mean(values) for values in by_task.values()]
    se = statistics.stdev(task_deltas) / math.sqrt(len(task_deltas))
    rows.append(
        [
            "Task-balanced mean",
            "--",
            "--",
            f"{fmt(mean(task_deltas))} [{fmt(mean(task_deltas) - 1.96 * se)}, {fmt(mean(task_deltas) + 1.96 * se)}]",
            f"{sum(d > 0 for d in task_deltas)}/{len(task_deltas)}",
        ]
    )

    write_table(
        TABLE_DIR / "codex_native_skill_effect.tex",
        ["Model", "No skill", "With skill", "Task-paired delta", "Positive tasks"],
        rows,
        align="lrrrr",
    )


def task_mode(task_name: str) -> str:
    task_dir = next(TASK_DIR.glob(f"*/{task_name}"))
    with (task_dir / "task.toml").open("rb") as handle:
        return tomllib.load(handle)["metadata"].get("mode", "standard")


def generate_mode_skill_summary(deltas: list[dict[str, str]]) -> None:
    rows = []
    for model in ("gpt-5.4-mini", "gpt-5.5"):
        for mode in ("standard", "raw"):
            values = [
                as_float(row, "delta")
                for row in deltas
                if row["model"] == model and task_mode(row["task"]) == mode
            ]
            rows.append(
                [
                    model,
                    mode,
                    len(values),
                    fmt(mean(values)),
                    f"{sum(value > 0 for value in values)}/{len(values)}",
                ]
            )

    for mode in ("standard", "raw"):
        by_task: dict[str, list[float]] = defaultdict(list)
        for row in deltas:
            if task_mode(row["task"]) == mode:
                by_task[row["task"]].append(as_float(row, "delta"))
        task_values = [mean(values) for values in by_task.values()]
        rows.append(
            [
                "Task-balanced mean",
                mode,
                len(task_values),
                fmt(mean(task_values)),
                f"{sum(value > 0 for value in task_values)}/{len(task_values)}",
            ]
        )

    write_table(
        TABLE_DIR / "codex_mode_skill_effect.tex",
        ["Model", "Mode", "Tasks", "Mean delta", "Positive tasks"],
        rows,
        align="llrrr",
    )


def generate_key_precision_summary(cells: list[dict[str, str]]) -> None:
    rows = []
    for condition in ("no-skill", "with-skill"):
        selected = [
            row
            for row in cells
            if row["schema"] == "native" and row["condition"] == condition
        ]
        rows.append(
            [
                condition,
                len(selected),
                fmt(mean([as_float(row, "mean_key_precision") for row in selected])),
                sum(int(row["sum_extra_keys"]) for row in selected),
            ]
        )

    worst = sorted(
        [
            row
            for row in cells
            if row["schema"] == "native"
            and row["condition"] in {"no-skill", "with-skill"}
        ],
        key=lambda row: int(row["sum_extra_keys"]),
        reverse=True,
    )[:5]
    for row in worst:
        rows.append(
            [
                f"{row['task']} / {row['condition']} / {row['model']}",
                int(row["n"]),
                fmt(as_float(row, "mean_key_precision")),
                int(row["sum_extra_keys"]),
            ]
        )

    write_table(
        TABLE_DIR / "codex_key_precision.tex",
        ["Condition or worst cell", "Cells/runs", "Mean key precision", "Extra keys"],
        rows,
        align="lrrr",
    )


def generate_skill_wins(deltas: list[dict[str, str]]) -> None:
    by_task: dict[str, list[float]] = defaultdict(list)
    for row in deltas:
        by_task[row["task"]].append(as_float(row, "delta"))
    rows = [
        [task, fmt(delta)]
        for task, delta in sorted(
            ((task, mean(values)) for task, values in by_task.items()),
            key=lambda item: item[1],
            reverse=True,
        )[:10]
    ]
    write_table(
        TABLE_DIR / "codex_skill_gains.tex",
        ["Task", "Mean delta"],
        rows,
        align="lr",
    )


def generate_skill_declines(deltas: list[dict[str, str]]) -> None:
    by_task: dict[str, list[float]] = defaultdict(list)
    for row in deltas:
        by_task[row["task"]].append(as_float(row, "delta"))
    rows = [
        [task, fmt(delta)]
        for task, delta in sorted(
            ((task, mean(values)) for task, values in by_task.items()),
            key=lambda item: item[1],
        )[:8]
    ]
    write_table(
        TABLE_DIR / "codex_skill_declines.tex",
        ["Task", "Mean delta"],
        rows,
        align="lr",
    )


def generate_contamination_summary(contamination: list[dict[str, str]]) -> None:
    rows = []
    for label, key in (
        ("Average over matched tasks", None),
        ("suspected infection", "mimic-suspicion-infection"),
        ("Sepsis-3 raw", "mimic-sepsis3-raw"),
        ("KDIGO-48h", "mimic-kdigo-48h"),
        ("MELD-24h", "mimic-meld-24h"),
        ("ventilation", "mimic-ventilation"),
        ("vasopressor equivalents", "mimic-vasopressor-equivalents"),
    ):
        selected = (
            contamination
            if key is None
            else [row for row in contamination if row["task"] == key]
        )
        rows.append(
            [
                label,
                fmt(mean([as_float(row, "native_no_skill") for row in selected])),
                fmt(mean([as_float(row, "obfuscated_no_skill") for row in selected])),
                fmt(mean([as_float(row, "restructured_no_skill") for row in selected])),
            ]
        )
    write_table(
        TABLE_DIR / "codex_schema_probe.tex",
        ["Task", "Native", "Obfuscated", "Restructured"],
        rows,
        align="lrrr",
    )


def generate_skill_all_probe(cells: list[dict[str, str]]) -> None:
    index = {
        (row["task"], row["model"], row["condition"], row["schema"]): row
        for row in cells
    }
    rows = []
    for cell in cells:
        if cell["condition"] != "with-skill-all":
            continue
        no_skill = index.get((cell["task"], cell["model"], "no-skill", cell["schema"]))
        with_skill = index.get(
            (cell["task"], cell["model"], "with-skill", cell["schema"])
        )
        if not (no_skill and with_skill):
            continue
        all_reward = as_float(cell, "mean_reward")
        targeted = as_float(with_skill, "mean_reward")
        rows.append(
            [
                cell["task"],
                fmt(as_float(no_skill, "mean_reward")),
                fmt(targeted),
                fmt(all_reward),
                fmt(all_reward - targeted),
            ]
        )
    rows.sort(key=lambda row: float(row[-1]))
    write_table(
        TABLE_DIR / "codex_skill_all_probe.tex",
        ["Task", "No skill", "Targeted", "All skills", "All-targeted"],
        rows,
        align="lrrrr",
    )


def main() -> None:
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    generate_task_inventory()
    generate_task_details()
    runs = read_csv(ANALYSIS_DIR / "runs.csv")
    cells = read_csv(ANALYSIS_DIR / "cells.csv")
    deltas = read_csv(ANALYSIS_DIR / "native_skill_deltas.csv")
    contamination = read_csv(ANALYSIS_DIR / "contamination_summary.csv")
    generate_integrity_table(runs, cells)
    generate_native_skill_summary(runs, deltas)
    generate_mode_skill_summary(deltas)
    generate_key_precision_summary(cells)
    generate_skill_wins(deltas)
    generate_skill_declines(deltas)
    generate_contamination_summary(contamination)
    generate_skill_all_probe(cells)


if __name__ == "__main__":
    main()
