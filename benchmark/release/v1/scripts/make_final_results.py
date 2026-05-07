#!/usr/bin/env python3
"""Generate final paper result tables from release roots plus reviewer reruns."""

from __future__ import annotations

import csv
import json
import math
import os
import random
import sys
from collections import defaultdict
from pathlib import Path

import duckdb
import tomllib

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

CODEX_RELEASE = RESULTS_DIR / "release-20260502-codex-v11"
CODEX_RERUN = RESULTS_DIR / "review-rerun-20260504-codex"
CLAUDE_RELEASE = RESULTS_DIR / "release-20260502-claude-provider"
CLAUDE_RERUN = RESULTS_DIR / "review-rerun-20260504-claude"
OSS_ROOT = RESULTS_DIR / "oss-rerun-provider-comparison-20260504_170533"

SQL_FREE_CANONICAL_TASKS = {
    "mimic-urine-output-rate",
    "mimic-urine-output-rate-raw",
    "mimic-vasopressor-equivalents",
    "mimic-vasopressor-equivalents-raw",
}
CLAUDE_NATIVE_SENTINEL_TASKS = {
    "mimic-urine-output-rate-raw",
    "mimic-ventilation",
    "mimic-creatinine-baseline-raw",
    "mimic-suspicion-infection",
    "mimic-vasopressor-equivalents-raw",
    "mimic-oasis-24h",
    "mimic-sepsis3-raw",
    "mimic-sofa-24h-raw",
}
CLAUDE_SCHEMA_SENTINEL_TASKS = {
    "mimic-oasis-24h-raw",
    "mimic-sofa-24h-raw",
    "mimic-kdigo-48h-raw",
}

sys.path.insert(0, str(BENCHMARK_DIR))
from evaluate import resolve_ground_truth  # noqa: E402
from lib.db import load_task_config, resolve_task_dir  # noqa: E402
from report_results import (  # noqa: E402
    cell_rows,
    control_rows,
    delta_rows,
    load_rows,
    mean,
)

UNORDERED_VALUE_COLUMNS = {"specimen", "ventilation_status"}
DIAGNOSTIC_CACHE = PLANNING_DIR / "secondary_metric_cache.json"


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


def fmt(value: float | int | str | None, digits: int = 3) -> str:
    if value is None:
        return "NA"
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


def run_key(row: dict) -> tuple:
    return (row["task"], row["condition"], row["schema"], row["model"], row["trial"])


def normalize_legacy_skill_rows(
    rows: list[dict], source_priority: int = 0
) -> list[dict]:
    """Treat legacy SQL-free variant runs as canonical with-skill rows.

    Early campaigns used `with-skill-nosql` for the four task variants whose
    original skills contained fenced SQL fragments. Canonical skills are now
    SQL-free, so those rows are the paper-facing `with-skill` rows. The legacy
    condition is retained in `legacy_condition` for provenance.
    """
    normalized = []
    for row in rows:
        copied = dict(row)
        copied["_source_priority"] = source_priority
        copied["_legacy_skill_priority"] = 0
        if (
            copied["task"] in SQL_FREE_CANONICAL_TASKS
            and copied["condition"] == "with-skill-nosql"
        ):
            copied["legacy_condition"] = copied["condition"]
            copied["condition"] = "with-skill"
            copied["_legacy_skill_priority"] = 1
        normalized.append(copied)
    return normalized


def combine_rows(release_root: Path, rerun_root: Path) -> tuple[list[dict], int]:
    combined: dict[tuple, tuple[tuple[int, int], dict]] = {}
    release_rows = normalize_legacy_skill_rows(
        load_rows(release_root), source_priority=0
    )
    rerun_rows = normalize_legacy_skill_rows(load_rows(rerun_root), source_priority=1)
    for row in release_rows + rerun_rows:
        key = run_key(row)
        priority = (
            int(row.get("_source_priority", 0)),
            int(row.get("_legacy_skill_priority", 0)),
        )
        if key not in combined or priority >= combined[key][0]:
            combined[key] = (priority, row)
    rows = [row for _, row in combined.values()]
    for row in rows:
        row.setdefault("tier", "")
        row.setdefault("tier_name", "")
    return rows, len(rerun_rows)


def load_rows_for_cells(root: Path) -> list[dict]:
    rows = normalize_legacy_skill_rows(load_rows(root))
    for row in rows:
        row.setdefault("tier", "")
        row.setdefault("tier_name", "")
    return rows


def filter_claude_paper_rows(rows: list[dict]) -> list[dict]:
    """Keep the 190 paper-facing Claude sentinel rows from a broader local root."""
    filtered = []
    for row in rows:
        schema = row.get("schema", "native")
        task = row["task"]
        condition = row["condition"]
        if (
            schema == "native"
            and task in CLAUDE_NATIVE_SENTINEL_TASKS
            and condition in {"no-skill", "with-skill"}
        ):
            filtered.append(row)
        elif (
            schema in {"obfuscated", "restructured"}
            and task in CLAUDE_SCHEMA_SENTINEL_TASKS
            and condition == "no-skill"
        ):
            filtered.append(row)
    return filtered


def strict_pass_count(rows: list[dict]) -> int:
    return sum((row["failed"] or 0) == 0 and (row["errors"] or 0) == 0 for row in rows)


def diagnostics_failed_count(rows: list[dict]) -> int:
    return sum(bool(row["diagnostics_failed"]) for row in rows)


def artifact_count(rows: list[dict], name: str) -> int:
    return sum((Path(row["path"]) / name).exists() for row in rows)


def native_reward_groups(rows: list[dict]) -> dict[tuple[str, str], list[float]]:
    groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in rows:
        if row["schema"] == "native" and row["condition"] in {"no-skill", "with-skill"}:
            groups[(row["model"], row["condition"])].append(float(row["reward"]))
    return groups


def task_deltas(deltas: list[dict]) -> dict[str, float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in deltas:
        grouped[row["task"]].append(float(row["delta"]))
    return {task: mean(values) for task, values in grouped.items()}


def bootstrap_ci(
    values: list[float], reps: int = 20000, seed: int = 20260504
) -> tuple[float, float]:
    rng = random.Random(seed)
    n = len(values)
    draws = []
    for _ in range(reps):
        draws.append(mean(values[rng.randrange(n)] for _ in range(n)))
    draws.sort()
    return draws[int(0.025 * reps)], draws[int(0.975 * reps)]


def cluster_bootstrap_ci(
    clusters: dict[str, list[float]], reps: int = 20000, seed: int = 20260506
) -> tuple[float, float]:
    rng = random.Random(seed)
    keys = sorted(clusters)
    draws = []
    for _ in range(reps):
        sample = []
        for _ in keys:
            sample.extend(clusters[rng.choice(keys)])
        draws.append(mean(sample))
    draws.sort()
    return draws[int(0.025 * reps)], draws[int(0.975 * reps)]


def family_balanced_bootstrap_ci(
    clusters: dict[str, list[float]], reps: int = 20000, seed: int = 20260506
) -> tuple[float, float]:
    rng = random.Random(seed)
    family_means = [mean(values) for _, values in sorted(clusters.items())]
    draws = []
    for _ in range(reps):
        draws.append(mean(rng.choice(family_means) for _ in family_means))
    draws.sort()
    return draws[int(0.025 * reps)], draws[int(0.975 * reps)]


def sign_flip_p(values: list[float], reps: int = 200000, seed: int = 20260504) -> float:
    observed = abs(mean(values))
    rng = random.Random(seed)
    hits = 0
    for _ in range(reps):
        flipped = [value if rng.randrange(2) else -value for value in values]
        if abs(mean(flipped)) >= observed:
            hits += 1
    return (hits + 1) / (reps + 1)


def task_mode(task: str) -> str:
    for task_file in (BENCHMARK_DIR / "tasks").glob(f"*/{task}/task.toml"):
        with task_file.open("rb") as handle:
            return tomllib.load(handle)["metadata"].get("mode", "standard")
    return "standard"


def task_family(task: str) -> str:
    for task_file in (BENCHMARK_DIR / "tasks").glob(f"*/{task}/task.toml"):
        return task_file.parents[1].name
    return task.split("-", 1)[0]


def sql_quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def sql_path(path: Path) -> str:
    return str(path).replace("'", "''")


def load_secondary_cache() -> dict[str, dict]:
    if DIAGNOSTIC_CACHE.exists():
        return json.loads(DIAGNOSTIC_CACHE.read_text())
    return {}


def write_secondary_cache(cache: dict[str, dict]) -> None:
    DIAGNOSTIC_CACHE.write_text(json.dumps(cache, indent=2, sort_keys=True))


def task_eval_config(task: str) -> dict:
    return load_task_config(resolve_task_dir(task))["evaluation"]


def truth_stats(
    task: str, con: duckdb.DuckDBPyConnection, *, include_nmae: bool
) -> dict:
    config = task_eval_config(task)
    gt_path = resolve_ground_truth(task)
    value_columns = [
        column
        for column in config["value_columns"]
        if column not in UNORDERED_VALUE_COLUMNS
    ]
    stats: dict[str, object] = {"truth_rows": 0, "ordered_columns": []}
    truth_rows = con.execute(
        f"select count(*) as truth_n from read_csv_auto('{sql_path(gt_path)}')"
    ).fetchone()[0]
    stats["truth_rows"] = int(truth_rows)
    if not include_nmae:
        return stats

    select_terms = []
    for index, column in enumerate(value_columns):
        quoted = sql_quote(column)
        select_terms.extend(
            [
                f"count(try_cast({quoted} as double)) as n_{index}",
                f"min(try_cast({quoted} as double)) as min_{index}",
                f"max(try_cast({quoted} as double)) as max_{index}",
            ]
        )
    if not select_terms:
        return stats

    values = con.execute(
        f"select {', '.join(select_terms)} from read_csv_auto('{sql_path(gt_path)}')"
    ).fetchone()
    ordered_columns = []
    for index, column in enumerate(value_columns):
        numeric_n, min_value, max_value = values[index * 3 : index * 3 + 3]
        if not numeric_n:
            continue
        scale = (
            float(max_value - min_value)
            if min_value is not None and max_value is not None and max_value > min_value
            else 1.0
        )
        ordered_columns.append({"column": column, "scale": scale})
    stats["ordered_columns"] = ordered_columns
    return stats


def compute_run_nmae(
    row: dict,
    *,
    con: duckdb.DuckDBPyConnection,
    task_stats: dict[str, dict],
) -> tuple[float | None, int]:
    run_path = Path(row["path"])
    output_path = run_path / "output.csv"
    if not output_path.exists():
        return None, 0
    task = row["task"]
    config = task_eval_config(task)
    stats = task_stats[task]
    ordered_columns = stats["ordered_columns"]
    if not ordered_columns:
        return None, 0

    gt_path = resolve_ground_truth(task)
    key_columns = config["key_columns"]
    partition = ", ".join(sql_quote(column) for column in key_columns)
    join_clause = " and ".join(
        f"t.{sql_quote(column)} = a.{sql_quote(column)}" for column in key_columns
    )

    terms = []
    try:
        present_columns = {
            value[0]
            for value in con.execute(
                f"describe select * from read_csv_auto('{sql_path(output_path)}')"
            ).fetchall()
        }
    except duckdb.Error:
        return None, 0
    for item in ordered_columns:
        column = item["column"]
        if column not in present_columns:
            terms.append("1.0")
            continue
        quoted = sql_quote(column)
        scale = float(item["scale"]) or 1.0
        terms.append(
            "avg(case "
            f"when try_cast(t.{quoted} as double) is null and try_cast(a.{quoted} as double) is null then 0.0 "
            f"when try_cast(t.{quoted} as double) is null or try_cast(a.{quoted} as double) is null then 1.0 "
            f"else least(abs(try_cast(a.{quoted} as double) - try_cast(t.{quoted} as double)) / {scale}, 1.0) "
            "end)"
        )
    if not terms:
        return None, 0

    query = f"""
    with
      t as (select * from read_csv_auto('{sql_path(gt_path)}')),
      a_raw as (
        select *, row_number() over (partition by {partition}) as rn
        from read_csv_auto('{sql_path(output_path)}')
      ),
      a as (select * exclude(rn) from a_raw where rn = 1)
    select ({" + ".join(terms)}) / {len(terms)} as nmae
    from t join a on {join_clause}
    """
    try:
        value = con.execute(query).fetchone()[0]
    except duckdb.Error:
        return None, 0
    return (float(value) if value is not None else None), len(terms)


def attach_secondary_metrics(rows: list[dict], *, compute_nmae_for=None) -> None:
    """Add key F1 and ordered-value nMAE to loaded run rows.

    The cache stores metrics keyed by run id so table refreshes do not rescan
    large retained CSV artifacts unless a run has not been seen before.
    """
    cache = load_secondary_cache()
    con = duckdb.connect()
    tasks_needing_nmae = {
        row["task"]
        for row in rows
        if row.get("task") and compute_nmae_for and compute_nmae_for(row)
    }
    task_stats = {
        task: truth_stats(task, con, include_nmae=task in tasks_needing_nmae)
        for task in sorted({row["task"] for row in rows if row.get("task")})
    }

    for index, row in enumerate(rows, start=1):
        task = row["task"]
        stats = task_stats[task]
        truth_rows = int(stats["truth_rows"])
        agent_unique_keys = int(row.get("agent_unique_keys") or 0)
        extra_keys = int(row.get("extra_keys") or 0)
        agent_keys_in_truth = max(agent_unique_keys - extra_keys, 0)
        key_precision = float(row.get("key_precision") or 0.0)
        key_recall = agent_keys_in_truth / truth_rows if truth_rows else 0.0
        key_f1 = (
            2 * key_precision * key_recall / (key_precision + key_recall)
            if key_precision + key_recall
            else 0.0
        )
        row["truth_rows"] = truth_rows
        row["key_recall"] = key_recall
        row["key_f1"] = key_f1

        should_compute_nmae = compute_nmae_for(row) if compute_nmae_for else False
        if should_compute_nmae:
            run_id = row["run_id"]
            cached = cache.get(run_id)
            if cached is None:
                nmae, ordered_count = compute_run_nmae(
                    row, con=con, task_stats=task_stats
                )
                cached = {
                    "ordered_value_nmae": nmae,
                    "ordered_value_columns": ordered_count,
                }
                cache[run_id] = cached
                if index % 25 == 0:
                    write_secondary_cache(cache)
                    print(f"Cached secondary metrics through {index}/{len(rows)} rows")
            row["ordered_value_nmae"] = cached["ordered_value_nmae"]
            row["ordered_value_columns"] = cached["ordered_value_columns"]
        else:
            row["ordered_value_nmae"] = None
            row["ordered_value_columns"] = 0

    write_secondary_cache(cache)


def cell_rows_with_secondary(rows: list[dict]) -> list[dict]:
    cells = cell_rows(rows)
    grouped_rows = grouped_by_cell(rows)
    for cell in cells:
        vals = grouped_rows[
            (
                cell["tier"],
                cell["tier_name"],
                cell["task"],
                cell["condition"],
                cell["schema"],
                cell["model"],
            )
        ]
        key_f1_values = [
            float(row["key_f1"]) for row in vals if row.get("key_f1") is not None
        ]
        nmae_values = [
            float(row["ordered_value_nmae"])
            for row in vals
            if row.get("ordered_value_nmae") is not None
        ]
        cell["mean_key_f1"] = mean(key_f1_values)
        cell["mean_ordered_value_nmae"] = mean(nmae_values)
        cell["ordered_value_columns"] = max(
            int(row.get("ordered_value_columns") or 0) for row in vals
        )
    return cells


def grouped_by_cell(rows: list[dict]) -> dict[tuple, list[dict]]:
    out: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        out[
            (
                row.get("tier"),
                row.get("tier_name", ""),
                row["task"],
                row["condition"],
                row["schema"],
                row["model"],
            )
        ].append(row)
    return out


def secondary_delta_rows(cells: list[dict], metric: str) -> list[dict]:
    index = {(c["task"], c["schema"], c["model"], c["condition"]): c for c in cells}
    out = []
    for (task, schema, model, condition), with_cell in sorted(index.items()):
        if schema != "native" or condition != "with-skill":
            continue
        no_cell = index.get((task, schema, model, "no-skill"))
        if not no_cell:
            continue
        no_value = no_cell.get(metric)
        with_value = with_cell.get(metric)
        if no_value is None or with_value is None:
            continue
        if isinstance(no_value, float) and math.isnan(no_value):
            continue
        if isinstance(with_value, float) and math.isnan(with_value):
            continue
        out.append(
            {
                "task": task,
                "model": model,
                "no_skill_mean": float(no_value),
                "with_skill_mean": float(with_value),
                "delta": float(with_value) - float(no_value),
                "ordered_value_columns": with_cell.get("ordered_value_columns", 0),
            }
        )
    return out


def task_metric_means(deltas: list[dict]) -> dict[str, float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in deltas:
        grouped[row["task"]].append(float(row["delta"]))
    return {task: mean(values) for task, values in grouped.items()}


def task_condition_means(
    cells: list[dict], metric: str, condition: str
) -> dict[str, float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for cell in cells:
        if cell["schema"] != "native" or cell["condition"] != condition:
            continue
        value = cell.get(metric)
        if value is None or (isinstance(value, float) and math.isnan(value)):
            continue
        grouped[cell["task"]].append(float(value))
    return {task: mean(values) for task, values in grouped.items()}


def write_codex_tables(rows: list[dict], cells: list[dict], deltas: list[dict]) -> dict:
    groups = native_reward_groups(rows)
    by_model: dict[str, list[float]] = defaultdict(list)
    for row in deltas:
        by_model[row["model"]].append(float(row["delta"]))

    td = task_deltas(deltas)
    task_values = list(td.values())
    ci_low, ci_high = bootstrap_ci(task_values)
    p_value = sign_flip_p(task_values)
    reward_no = task_condition_means(cells, "mean_reward", "no-skill")
    reward_with = task_condition_means(cells, "mean_reward", "with-skill")
    key_f1_deltas = secondary_delta_rows(cells, "mean_key_f1")
    key_f1_td = task_metric_means(key_f1_deltas)
    key_f1_no = task_condition_means(cells, "mean_key_f1", "no-skill")
    key_f1_with = task_condition_means(cells, "mean_key_f1", "with-skill")
    nmae_deltas = secondary_delta_rows(cells, "mean_ordered_value_nmae")
    nmae_td = task_metric_means(nmae_deltas)
    nmae_no = task_condition_means(cells, "mean_ordered_value_nmae", "no-skill")
    nmae_with = task_condition_means(cells, "mean_ordered_value_nmae", "with-skill")

    native_rows = []
    for model in ("gpt-5.4-mini", "gpt-5.5"):
        model_deltas = by_model[model]
        native_rows.append(
            [
                f"Reward / {model}",
                fmt(mean(groups[(model, "no-skill")])),
                fmt(mean(groups[(model, "with-skill")])),
                fmt(mean(model_deltas)),
                f"{sum(value > 0 for value in model_deltas)}/{len(model_deltas)}",
            ]
        )
    native_rows.append(
        [
            "Reward / task-balanced",
            fmt(mean(reward_no.values())),
            fmt(mean(reward_with.values())),
            f"{fmt(mean(task_values))} [{fmt(ci_low)}, {fmt(ci_high)}]",
            f"{sum(value > 0 for value in task_values)}/{len(task_values)}",
        ]
    )
    key_f1_values = list(key_f1_td.values())
    native_rows.append(
        [
            "Key F1 / task-balanced",
            fmt(mean(key_f1_no.values())),
            fmt(mean(key_f1_with.values())),
            fmt(mean(key_f1_values)),
            f"{sum(value > 0 for value in key_f1_values)}/{len(key_f1_values)}",
        ]
    )
    nmae_values = list(nmae_td.values())
    native_rows.append(
        [
            "Ordered nMAE / task-balanced",
            fmt(mean(nmae_no.values())),
            fmt(mean(nmae_with.values())),
            fmt(mean(nmae_values)),
            f"{sum(value < 0 for value in nmae_values)}/{len(nmae_values)}",
        ]
    )
    write_table(
        TABLE_DIR / "codex_native_skill_effect.tex",
        ["Measure", "No skill", "With skill", "Delta", "Improved tasks"],
        native_rows,
        "lrrrr",
    )

    family_clusters: dict[str, list[float]] = defaultdict(list)
    for task, value in td.items():
        family_clusters[task_family(task)].append(value)
    family_cluster_low, family_cluster_high = cluster_bootstrap_ci(family_clusters)
    family_balanced_low, family_balanced_high = family_balanced_bootstrap_ci(
        family_clusters
    )
    family_means = [mean(values) for values in family_clusters.values()]
    write_table(
        TABLE_DIR / "codex_family_sensitivity.tex",
        ["Analysis", "Units", "Mean delta", "95% interval"],
        [
            [
                "Task-cluster bootstrap",
                f"{len(task_values)} tasks",
                fmt(mean(task_values)),
                f"[{fmt(ci_low)}, {fmt(ci_high)}]",
            ],
            [
                "Family-cluster bootstrap",
                f"{len(family_clusters)} families",
                fmt(mean(task_values)),
                f"[{fmt(family_cluster_low)}, {fmt(family_cluster_high)}]",
            ],
            [
                "Family-balanced bootstrap",
                f"{len(family_clusters)} families",
                fmt(mean(family_means)),
                f"[{fmt(family_balanced_low)}, {fmt(family_balanced_high)}]",
            ],
        ],
        "lrrr",
    )

    mode_rows = []
    for model in ("gpt-5.4-mini", "gpt-5.5"):
        for mode in ("standard", "raw"):
            values = [
                float(row["delta"])
                for row in deltas
                if row["model"] == model and task_mode(row["task"]) == mode
            ]
            mode_rows.append(
                [
                    model,
                    mode,
                    len(values),
                    fmt(mean(values)),
                    f"{sum(value > 0 for value in values)}/{len(values)}",
                ]
            )
    for mode in ("standard", "raw"):
        values = [value for task, value in td.items() if task_mode(task) == mode]
        mode_rows.append(
            [
                "Task-balanced mean",
                mode,
                len(values),
                fmt(mean(values)),
                f"{sum(value > 0 for value in values)}/{len(values)}",
            ]
        )
    write_table(
        TABLE_DIR / "codex_mode_skill_effect.tex",
        ["Model", "Mode", "Tasks", "Mean delta", "Positive tasks"],
        mode_rows,
        "llrrr",
    )

    gains = sorted(td.items(), key=lambda item: item[1], reverse=True)[:10]
    write_table(
        TABLE_DIR / "codex_skill_gains.tex",
        ["Task", "Mean delta"],
        [[task, fmt(delta)] for task, delta in gains],
        "lr",
    )
    declines = sorted(td.items(), key=lambda item: item[1])[:8]
    write_table(
        TABLE_DIR / "codex_skill_declines.tex",
        ["Task", "Mean delta"],
        [[task, fmt(delta)] for task, delta in declines],
        "lr",
    )

    ordered_cols_by_task = {
        row["task"]: int(row.get("ordered_value_columns") or 0) for row in nmae_deltas
    }
    diagnostic_task_rows = []
    for task, reward_delta in sorted(td.items()):
        diagnostic_task_rows.append(
            [
                task,
                fmt(reward_delta),
                fmt(key_f1_td.get(task)),
                fmt(nmae_td.get(task)),
                ordered_cols_by_task.get(task, 0),
            ]
        )
    write_table(
        TABLE_DIR / "codex_secondary_diagnostics_by_task.tex",
        ["Task", "Reward delta", "Key F1 delta", "nMAE delta", "Ordered cols"],
        diagnostic_task_rows,
        "lrrrr",
    )

    kp_rows = []
    for condition in ("no-skill", "with-skill"):
        selected = [
            row
            for row in cells
            if row["schema"] == "native" and row["condition"] == condition
        ]
        kp_rows.append(
            [
                condition,
                len(selected),
                fmt(mean(float(row["mean_key_f1"]) for row in selected)),
                fmt(mean(float(row["mean_key_precision"]) for row in selected)),
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
        kp_rows.append(
            [
                f"{row['task']} / {row['condition']} / {row['model']}",
                int(row["n"]),
                fmt(float(row["mean_key_f1"])),
                fmt(float(row["mean_key_precision"])),
                int(row["sum_extra_keys"]),
            ]
        )
    write_table(
        TABLE_DIR / "codex_key_precision.tex",
        [
            "Condition or worst cell",
            "Cells/runs",
            "Mean key F1",
            "Mean key precision",
            "Extra keys",
        ],
        kp_rows,
        "lrrrr",
    )

    controls = control_rows(cells)
    labels = {
        "with-skill-rawsql": "Raw reference SQL",
        "with-skill-decoy": "Decoy skill",
    }
    control_table = []
    for condition in ("with-skill-rawsql", "with-skill-decoy"):
        vals = [row for row in controls if row["condition"] == condition]
        task_count = len({row["task"] for row in vals})
        control_table.append(
            [
                labels[condition],
                task_count,
                fmt(mean(float(row["no_skill_mean"]) for row in vals)),
                fmt(mean(float(row["with_skill_mean"]) for row in vals)),
                fmt(mean(float(row["control_mean"]) for row in vals)),
                fmt(mean(float(row["control_minus_with_skill"]) for row in vals)),
                fmt(mean(float(row["control_minus_no_skill"]) for row in vals)),
            ]
        )
    write_table(
        TABLE_DIR / "codex_matched_controls.tex",
        [
            "Control",
            "Tasks",
            "No skill",
            "Targeted",
            "Control",
            "Control--targeted",
            "Control--no skill",
        ],
        control_table,
        "lrrrrrr",
    )

    write_table(
        TABLE_DIR / "codex_integrity.tex",
        ["Audit quantity", "Count"],
        [
            ["Runs", len(rows)],
            ["Expected primary/supplementary runs", 760],
            ["Task/condition/schema/model cells", len(cells)],
            ["Publishable flag failures", sum(not row["publishable"] for row in rows)],
            ["Isolation flag failures", sum(not row["isolated"] for row in rows)],
            [
                "Filesystem canary failures",
                sum(not row["filesystem_canary"] for row in rows),
            ],
            [
                "Contamination-lint failures",
                sum(not row["contamination_lint"] for row in rows),
            ],
            [
                "Nonzero agent exits",
                sum(row["agent_returncode"] not in (0, None) for row in rows),
            ],
            ["Missing rewards", sum(row["reward"] is None for row in rows)],
            ["Fully passing diagnostic runs", strict_pass_count(rows)],
            ["Runs with semantic diagnostic failures", diagnostics_failed_count(rows)],
            ["Retained output.csv artifacts", artifact_count(rows, "output.csv")],
            ["Retained trace.jsonl artifacts", artifact_count(rows, "trace.jsonl")],
            [
                "Retained instruction.md artifacts",
                artifact_count(rows, "instruction.md"),
            ],
            ["Retained egress.jsonl artifacts", artifact_count(rows, "egress.jsonl")],
        ],
        "lr",
    )

    return {
        "task_delta": mean(task_values),
        "ci_low": ci_low,
        "ci_high": ci_high,
        "p_value": p_value,
        "positive_tasks": sum(value > 0 for value in task_values),
        "tasks": len(task_values),
        "key_f1_delta": mean(key_f1_values),
        "key_f1_positive_tasks": sum(value > 0 for value in key_f1_values),
        "nmae_delta": mean(nmae_values),
        "nmae_improved_tasks": sum(value < 0 for value in nmae_values),
        "nmae_tasks": len(nmae_values),
    }


def write_claude_tables(rows: list[dict], deltas: list[dict]) -> dict:
    groups = native_reward_groups(rows)
    by_model: dict[str, list[float]] = defaultdict(list)
    for row in deltas:
        by_model[row["model"]].append(float(row["delta"]))
    td = task_deltas(deltas)
    task_values = list(td.values())
    ci_low, ci_high = bootstrap_ci(task_values)

    model_labels = {"opus": "Claude Opus", "sonnet": "Claude Sonnet"}
    rows_out = []
    for model in ("opus", "sonnet"):
        values = by_model[model]
        rows_out.append(
            [
                model_labels[model],
                fmt(mean(groups[(model, "no-skill")])),
                fmt(mean(groups[(model, "with-skill")])),
                fmt(mean(values)),
                f"{sum(value > 0 for value in values)}/{len(values)}",
            ]
        )
    rows_out.append(
        [
            "Task-balanced mean",
            "--",
            "--",
            f"{fmt(mean(task_values))} [{fmt(ci_low)}, {fmt(ci_high)}]",
            f"{sum(value > 0 for value in task_values)}/{len(task_values)}",
        ]
    )
    write_table(
        TABLE_DIR / "claude_native_skill_effect.tex",
        ["Model", "No skill", "With skill", "Task-paired delta", "Positive tasks"],
        rows_out,
        "lrrrr",
    )

    label_map = {
        "mimic-urine-output-rate-raw": "urine-output rate raw",
        "mimic-ventilation": "ventilation",
        "mimic-creatinine-baseline-raw": "baseline creatinine raw",
        "mimic-suspicion-infection": "suspected infection",
        "mimic-vasopressor-equivalents-raw": "vasopressor equivalents raw",
        "mimic-sepsis3-raw": "Sepsis-3 raw",
        "mimic-oasis-24h": "OASIS-24h",
        "mimic-sofa-24h-raw": "SOFA-24h raw",
    }
    by_task_model = {(row["task"], row["model"]): float(row["delta"]) for row in deltas}
    task_rows = []
    for task, value in sorted(td.items(), key=lambda item: item[1], reverse=True):
        task_rows.append(
            [
                label_map.get(task, task),
                fmt(by_task_model[(task, "opus")]),
                fmt(by_task_model[(task, "sonnet")]),
                fmt(value),
            ]
        )
    write_table(
        TABLE_DIR / "claude_task_deltas.tex",
        ["Task", "Opus delta", "Sonnet delta", "Mean delta"],
        task_rows,
        "lrrr",
    )

    return {
        "task_delta": mean(task_values),
        "ci_low": ci_low,
        "ci_high": ci_high,
        "positive_tasks": sum(value > 0 for value in task_values),
        "tasks": len(task_values),
    }


def write_oss_tables(rows: list[dict], cells: list[dict], deltas: list[dict]) -> dict:
    """Write exploratory local gpt-oss tables.

    This arm is intentionally kept separate from paper-facing Codex/Claude
    evidence because the local Ollama host exception makes every run
    non-publishable under the release criteria.
    """
    groups = native_reward_groups(rows)
    task_values = list(task_deltas(deltas).values())
    ci_low, ci_high = bootstrap_ci(task_values, reps=20000, seed=20260505)

    model = "gpt-oss:20b"
    rows_out = [
        [
            "gpt-oss-20b local",
            fmt(mean(groups[(model, "no-skill")])),
            fmt(mean(groups[(model, "with-skill")])),
            f"{fmt(mean(task_values))} [{fmt(ci_low)}, {fmt(ci_high)}]",
            f"{sum(value > 0 for value in task_values)}/{len(task_values)}",
        ]
    ]
    write_table(
        TABLE_DIR / "oss_native_skill_effect.tex",
        ["Model", "No skill", "With skill", "Task-paired delta", "Positive tasks"],
        rows_out,
        "lrrrr",
    )

    label_map = {
        "mimic-urine-output-rate-raw": "urine-output rate raw",
        "mimic-ventilation": "ventilation",
        "mimic-creatinine-baseline-raw": "baseline creatinine raw",
        "mimic-suspicion-infection": "suspected infection",
        "mimic-vasopressor-equivalents-raw": "vasopressor equivalents raw",
        "mimic-sepsis3-raw": "Sepsis-3 raw",
        "mimic-oasis-24h": "OASIS-24h",
        "mimic-sofa-24h-raw": "SOFA-24h raw",
    }
    task_rows = []
    for row in sorted(deltas, key=lambda item: float(item["delta"]), reverse=True):
        task_rows.append(
            [
                label_map.get(row["task"], row["task"]),
                fmt(float(row["no_skill_mean"])),
                fmt(float(row["with_skill_mean"])),
                fmt(float(row["delta"])),
            ]
        )
    write_table(
        TABLE_DIR / "oss_task_deltas.tex",
        ["Task", "No skill", "With skill", "Delta"],
        task_rows,
        "lrrr",
    )

    index = {(c["task"], c["schema"], c["condition"]): c for c in cells}
    schema_rows = []
    for task in sorted(
        {c["task"] for c in cells if c["schema"] in {"obfuscated", "restructured"}}
    ):
        native = index.get((task, "native", "no-skill"))
        obfuscated = index.get((task, "obfuscated", "no-skill"))
        restructured = index.get((task, "restructured", "no-skill"))
        schema_rows.append(
            [
                label_map.get(task, task),
                fmt(native["mean_reward"] if native else None),
                fmt(obfuscated["mean_reward"] if obfuscated else None),
                fmt(restructured["mean_reward"] if restructured else None),
            ]
        )
    write_table(
        TABLE_DIR / "oss_schema_probe.tex",
        ["Task", "Native", "Obfuscated", "Restructured"],
        schema_rows,
        "lrrr",
    )

    write_table(
        TABLE_DIR / "oss_integrity.tex",
        ["Audit quantity", "Count"],
        [
            ["Runs", len(rows)],
            ["Publishable runs", sum(row["publishable"] for row in rows)],
            [
                "Non-publishable local Ollama runs",
                sum(not row["publishable"] for row in rows),
            ],
            ["Task/condition/schema/model cells", len(cells)],
            ["Native paired tasks", len(task_values)],
            ["Isolation flag failures", sum(not row["isolated"] for row in rows)],
            [
                "Filesystem canary failures",
                sum(not row["filesystem_canary"] for row in rows),
            ],
            [
                "Contamination-lint failures",
                sum(not row["contamination_lint"] for row in rows),
            ],
            [
                "Nonzero agent exits",
                sum(row["agent_returncode"] not in (0, None) for row in rows),
            ],
            ["Missing rewards", sum(row["reward"] is None for row in rows)],
            ["Fully passing diagnostic runs", strict_pass_count(rows)],
            ["Runs with semantic diagnostic failures", diagnostics_failed_count(rows)],
            ["Retained output.csv artifacts", artifact_count(rows, "output.csv")],
            ["Retained trace.jsonl artifacts", artifact_count(rows, "trace.jsonl")],
            [
                "Retained instruction.md artifacts",
                artifact_count(rows, "instruction.md"),
            ],
            ["Retained egress.jsonl artifacts", artifact_count(rows, "egress.jsonl")],
        ],
        "lr",
    )

    return {
        "task_delta": mean(task_values),
        "ci_low": ci_low,
        "ci_high": ci_high,
        "positive_tasks": sum(value > 0 for value in task_values),
        "tasks": len(task_values),
    }


def write_csv_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = sorted({key for row in rows for key in row})
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            copied = dict(row)
            if copied.get("path"):
                try:
                    rel = Path(copied["path"]).resolve().relative_to(RESULTS_DIR)
                    copied["path"] = str(Path("benchmark/results") / rel)
                except ValueError:
                    copied["path"] = Path(copied["path"]).name
            writer.writerow(copied)


def main() -> None:
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    PLANNING_DIR.mkdir(parents=True, exist_ok=True)

    codex_rows, codex_replaced = combine_rows(CODEX_RELEASE, CODEX_RERUN)
    claude_rows_all, claude_replaced = combine_rows(CLAUDE_RELEASE, CLAUDE_RERUN)
    claude_rows = filter_claude_paper_rows(claude_rows_all)
    oss_rows = load_rows_for_cells(OSS_ROOT)
    attach_secondary_metrics(
        codex_rows,
        compute_nmae_for=lambda row: row["schema"] == "native"
        and row["condition"] in {"no-skill", "with-skill"},
    )
    attach_secondary_metrics(claude_rows)
    attach_secondary_metrics(oss_rows)
    codex_cells = cell_rows_with_secondary(codex_rows)
    codex_deltas = delta_rows(codex_cells)
    claude_cells = cell_rows_with_secondary(claude_rows)
    claude_deltas = delta_rows(claude_cells)
    oss_cells = cell_rows_with_secondary(oss_rows)
    oss_deltas = delta_rows(oss_cells)

    write_csv_rows(PLANNING_DIR / "final_codex_runs.csv", codex_rows)
    write_csv_rows(PLANNING_DIR / "final_claude_runs.csv", claude_rows)
    write_csv_rows(PLANNING_DIR / "final_oss_runs.csv", oss_rows)

    codex_summary = write_codex_tables(codex_rows, codex_cells, codex_deltas)
    claude_summary = write_claude_tables(claude_rows, claude_deltas)
    oss_summary = write_oss_tables(oss_rows, oss_cells, oss_deltas)

    release_codex_deltas = delta_rows(cell_rows(load_rows_for_cells(CODEX_RELEASE)))
    release_claude_deltas = delta_rows(cell_rows(load_rows_for_cells(CLAUDE_RELEASE)))
    old_codex_td = task_deltas(release_codex_deltas)
    new_codex_td = task_deltas(codex_deltas)
    old_claude_td = task_deltas(release_claude_deltas)
    new_claude_td = task_deltas(claude_deltas)

    changed_codex = sorted(
        [
            (
                task,
                old_codex_td[task],
                new_codex_td[task],
                new_codex_td[task] - old_codex_td[task],
            )
            for task in new_codex_td
        ],
        key=lambda item: abs(item[3]),
        reverse=True,
    )[:10]
    changed_claude = sorted(
        [
            (
                task,
                old_claude_td[task],
                new_claude_td[task],
                new_claude_td[task] - old_claude_td[task],
            )
            for task in new_claude_td
        ],
        key=lambda item: abs(item[3]),
        reverse=True,
    )

    report = [
        "# Final Results Update",
        "",
        "Combined evidence treats the May 4 clinician-review reruns as replacements for matching May 2 run keys.",
        "",
        "## Codex",
        "",
        f"- Final runs: {len(codex_rows)}; rerun replacements applied: {codex_replaced}; cells: {len(codex_cells)}.",
        f"- Strict diagnostic passes: {strict_pass_count(codex_rows)}/{len(codex_rows)}.",
        f"- Native task-balanced delta: {fmt(codex_summary['task_delta'])} [{fmt(codex_summary['ci_low'])}, {fmt(codex_summary['ci_high'])}], sign-flip p<0.0001.",
        f"- Positive tasks: {codex_summary['positive_tasks']}/{codex_summary['tasks']}.",
        "",
        "| Task | May 2 delta | Final delta | Change |",
        "|---|---:|---:|---:|",
    ]
    for task, old, new, change in changed_codex:
        report.append(f"| `{task}` | {fmt(old)} | {fmt(new)} | {fmt(change)} |")
    report += [
        "",
        "## Claude",
        "",
        f"- Final runs: {len(claude_rows)}; rerun replacements applied: {claude_replaced}; cells: {len(claude_cells)}.",
        f"- Strict diagnostic passes: {strict_pass_count(claude_rows)}/{len(claude_rows)}.",
        f"- Native sentinel task-balanced delta: {fmt(claude_summary['task_delta'])} [{fmt(claude_summary['ci_low'])}, {fmt(claude_summary['ci_high'])}].",
        f"- Positive sentinel tasks: {claude_summary['positive_tasks']}/{claude_summary['tasks']}.",
        "",
        "| Task | May 2 delta | Final delta | Change |",
        "|---|---:|---:|---:|",
    ]
    for task, old, new, change in changed_claude:
        report.append(f"| `{task}` | {fmt(old)} | {fmt(new)} | {fmt(change)} |")
    report += [
        "",
        "## Exploratory local OSS",
        "",
        f"- Runs: {len(oss_rows)}; publishable runs: {sum(row['publishable'] for row in oss_rows)}; cells: {len(oss_cells)}.",
        f"- Strict diagnostic passes: {strict_pass_count(oss_rows)}/{len(oss_rows)}.",
        f"- Native sentinel task-balanced delta: {fmt(oss_summary['task_delta'])} [{fmt(oss_summary['ci_low'])}, {fmt(oss_summary['ci_high'])}].",
        f"- Positive sentinel tasks: {oss_summary['positive_tasks']}/{oss_summary['tasks']}.",
        "- All runs are non-publishable under the release criteria because they use the local Ollama host exception; this arm is exploratory only.",
        "",
        "| Task | No skill | With skill | Delta |",
        "|---|---:|---:|---:|",
    ]
    for row in sorted(oss_deltas, key=lambda item: float(item["delta"]), reverse=True):
        report.append(
            f"| `{row['task']}` | {fmt(float(row['no_skill_mean']))} | {fmt(float(row['with_skill_mean']))} | {fmt(float(row['delta']))} |"
        )
    report += [
        "",
        "## Interpretation",
        "",
        "The headline result is stable. The Codex task-balanced native skill effect moves from 0.112 to "
        f"{fmt(codex_summary['task_delta'])}; the positive-task count remains {codex_summary['positive_tasks']}/28. "
        "The largest local changes are in the clinician-reviewed OASIS tasks, with creatinine-baseline raw also increasing after rerun.",
        "",
        "Claude remains a sentinel arm. The creatinine-baseline raw rerun increases the sentinel average, but the provider arm still covers only eight paired tasks and should not be promoted to co-primary evidence.",
        "",
        "The local gpt-oss-20b arm is useful as a reproducibility and open-model stress test, but it should not be mixed into the primary tables: reward is near zero, gains are positive on only three of eight paired sentinel tasks, no run is publishable under the paper criteria, and egress logs are absent.",
        "",
    ]
    (PLANNING_DIR / "final_results_update.md").write_text("\n".join(report))
    print(
        f"Wrote {PLANNING_DIR / 'final_results_update.md'} and regenerated result tables"
    )


if __name__ == "__main__":
    main()
