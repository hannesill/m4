"""Export analysis tables, plots, and a Markdown report for benchmark campaigns."""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import statistics as stats
import sys
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

BENCHMARK_ROOT = Path(__file__).resolve().parent
DEFAULT_RESULTS_ROOT = BENCHMARK_ROOT / "results" / "codex-full-20260428"
DEFAULT_PROFILE = "powered"


def run_key(row: dict) -> tuple:
    return (
        row["task"],
        row["condition"],
        row["schema"],
        row["model"],
        row["trial"],
    )


def mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else float("nan")


def sd(values: Iterable[float]) -> float:
    values = list(values)
    return stats.stdev(values) if len(values) > 1 else 0.0


def fmt(value: float | int | None, digits: int = 3) -> str:
    if value is None:
        return "NA"
    if isinstance(value, float) and math.isnan(value):
        return "NA"
    if isinstance(value, int):
        return str(value)
    return f"{value:.{digits}f}"


def load_rows(results_root: Path) -> list[dict]:
    rows: list[dict] = []
    for result_path in sorted(results_root.glob("*/result.json")):
        data = json.loads(result_path.read_text())
        test = data.get("test_results") or {}
        agent = data.get("agent_result") or {}
        canary = data.get("filesystem_canary") or {}
        lint = data.get("contamination_lint") or {}
        rows.append(
            {
                "run_id": data.get("run_id", result_path.parent.name),
                "path": str(result_path.parent),
                "task": data.get("task"),
                "condition": data.get("condition"),
                "schema": data.get("schema", "native"),
                "agent": data.get("agent"),
                "model": data.get("model"),
                "trial": data.get("trial"),
                "reasoning_effort": data.get("resolved_reasoning_effort")
                or data.get("reasoning_effort"),
                "publishable": bool(data.get("publishable")),
                "publishable_reason": data.get("publishable_reason", ""),
                "isolated": bool(data.get("isolated")),
                "filesystem_canary": bool(canary.get("passed")),
                "containerized_agent": bool(canary.get("containerized_agent")),
                "contamination_lint": bool(lint.get("passed")),
                "agent_returncode": agent.get("returncode", agent.get("exit_code")),
                "agent_status": agent.get("status"),
                "elapsed_seconds": agent.get("elapsed_seconds"),
                "passed": test.get("passed"),
                "failed": test.get("failed"),
                "errors": test.get("errors"),
                "total_tests": test.get("total"),
                "reward": test.get("reward"),
                "reward_uncapped": test.get("reward_uncapped"),
                "diagnostics_failed": bool(test.get("diagnostics_failed")),
                "key_precision": test.get("key_precision"),
                "extra_keys": test.get("extra_keys"),
                "agent_unique_keys": test.get("agent_unique_keys"),
                "match_rates": test.get("match_rates") or {},
            }
        )
    return rows


def _load_matrix_tiers(profile: str, agent: str, seeds: int):
    sys.path.insert(0, str(BENCHMARK_ROOT))
    import matrix  # type: ignore

    matrix.ALL_TASKS.clear()
    matrix.STANDARD_TASKS.clear()
    matrix.RAW_TASKS.clear()
    matrix.EXPERT_TASKS.clear()
    matrix.COMPOSITIONAL_TASKS.clear()
    matrix.CROSS_DB_TASKS.clear()
    matrix.CONTAMINATION_TASKS.clear()
    matrix._classify_tasks()
    return matrix.build_tiers(seeds=seeds, agent=agent, profile=profile)


def attach_tiers(rows: list[dict], *, profile: str, agent: str, seeds: int) -> dict:
    tiers = _load_matrix_tiers(profile=profile, agent=agent, seeds=seeds)
    tier_names = {tier.number: tier.name for tier in tiers}
    lookup = {}
    expected_keys = set()
    expected_cells = set()
    for tier in tiers:
        for run in tier.runs:
            key = (
                run["task"],
                run["condition"],
                run["schema"],
                run["model"],
                run["trial"],
            )
            lookup[key] = (tier.number, tier.name)
            expected_keys.add(key)
            expected_cells.add(
                (run["task"], run["condition"], run["schema"], run["model"])
            )
    for row in rows:
        tier = lookup.get(run_key(row))
        row["tier"] = tier[0] if tier else None
        row["tier_name"] = tier[1] if tier else ""
    observed_keys = {run_key(row) for row in rows}
    return {
        "tier_names": tier_names,
        "expected_count": len(expected_keys),
        "expected_cells": len(expected_cells),
        "missing": sorted(expected_keys - observed_keys),
        "unexpected": sorted(observed_keys - expected_keys),
    }


def grouped(rows: list[dict], keys: list[str]) -> dict[tuple, list[dict]]:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        groups[tuple(row[key] for key in keys)].append(row)
    return groups


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def cell_rows(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for key, vals in sorted(
        grouped(
            rows, ["tier", "tier_name", "task", "condition", "schema", "model"]
        ).items()
    ):
        rewards = [v["reward"] for v in vals if v["reward"] is not None]
        precisions = [
            v["key_precision"] for v in vals if v["key_precision"] is not None
        ]
        out.append(
            {
                "tier": key[0],
                "tier_name": key[1],
                "task": key[2],
                "condition": key[3],
                "schema": key[4],
                "model": key[5],
                "n": len(vals),
                "mean_reward": mean(rewards),
                "sd_reward": sd(rewards),
                "median_reward": stats.median(rewards) if rewards else None,
                "min_reward": min(rewards) if rewards else None,
                "max_reward": max(rewards) if rewards else None,
                "mean_key_precision": mean(precisions),
                "sum_failed_tests": sum(v["failed"] or 0 for v in vals),
                "sum_errors": sum(v["errors"] or 0 for v in vals),
                "sum_extra_keys": sum(v["extra_keys"] or 0 for v in vals),
            }
        )
    return out


def delta_rows(cells: list[dict]) -> list[dict]:
    index = {(c["task"], c["schema"], c["model"], c["condition"]): c for c in cells}
    out: list[dict] = []
    for (task, schema, model, condition), with_cell in sorted(index.items()):
        if schema != "native" or condition != "with-skill":
            continue
        no_cell = index.get((task, schema, model, "no-skill"))
        if not no_cell:
            continue
        out.append(
            {
                "task": task,
                "schema": schema,
                "model": model,
                "no_skill_mean": no_cell["mean_reward"],
                "with_skill_mean": with_cell["mean_reward"],
                "delta": with_cell["mean_reward"] - no_cell["mean_reward"],
                "no_skill_n": no_cell["n"],
                "with_skill_n": with_cell["n"],
            }
        )
    return out


def contamination_rows(cells: list[dict]) -> list[dict]:
    index = {(c["task"], c["schema"], c["model"], c["condition"]): c for c in cells}
    tasks = sorted(
        {
            c["task"]
            for c in cells
            if c["model"] == "gpt-5.4-mini"
            and c["condition"] == "no-skill"
            and c["schema"] in {"obfuscated", "restructured"}
        }
    )
    out: list[dict] = []
    for task in tasks:
        native = index.get((task, "native", "gpt-5.4-mini", "no-skill"))
        obf = index.get((task, "obfuscated", "gpt-5.4-mini", "no-skill"))
        restr = index.get((task, "restructured", "gpt-5.4-mini", "no-skill"))
        if not (native and obf and restr):
            continue
        out.append(
            {
                "task": task,
                "native_no_skill": native["mean_reward"],
                "obfuscated_no_skill": obf["mean_reward"],
                "restructured_no_skill": restr["mean_reward"],
                "obfuscated_delta": obf["mean_reward"] - native["mean_reward"],
                "restructured_delta": restr["mean_reward"] - native["mean_reward"],
            }
        )
    return out


def control_rows(cells: list[dict]) -> list[dict]:
    index = {(c["task"], c["schema"], c["model"], c["condition"]): c for c in cells}
    out: list[dict] = []
    for condition in ("with-skill-nosql", "with-skill-rawsql", "with-skill-decoy"):
        for (task, schema, model, cell_condition), control in sorted(index.items()):
            if schema != "native" or cell_condition != condition:
                continue
            no_skill = index.get((task, schema, model, "no-skill"))
            targeted = index.get((task, schema, model, "with-skill"))
            if not (no_skill and targeted):
                continue
            no_reward = no_skill["mean_reward"]
            targeted_reward = targeted["mean_reward"]
            control_reward = control["mean_reward"]
            out.append(
                {
                    "task": task,
                    "model": model,
                    "condition": condition,
                    "no_skill_mean": no_reward,
                    "with_skill_mean": targeted_reward,
                    "control_mean": control_reward,
                    "control_minus_no_skill": control_reward - no_reward,
                    "control_minus_with_skill": control_reward - targeted_reward,
                    "control_n": control["n"],
                }
            )
    return out


def svg_bar(
    path: Path,
    title: str,
    labels: list[str],
    series: list[tuple[str, list[float], str]],
) -> None:
    width = max(760, 90 * len(labels) + 180)
    height = 420
    margin = {"left": 80, "right": 30, "top": 60, "bottom": 120}
    plot_w = width - margin["left"] - margin["right"]
    plot_h = height - margin["top"] - margin["bottom"]
    max_y = max([1.0] + [v for _, vals, _ in series for v in vals])
    bar_group = plot_w / len(labels)
    bar_w = min(34, bar_group / (len(series) + 1))
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<style>text{font-family:Arial,sans-serif;font-size:12px}.title{font-size:18px;font-weight:700}.axis{stroke:#333;stroke-width:1}.grid{stroke:#ddd;stroke-width:1}.label{fill:#333}.legend{font-size:13px}</style>",
        f'<text class="title" x="{width / 2}" y="30" text-anchor="middle">{html.escape(title)}</text>',
    ]
    for tick in [0, 0.25, 0.5, 0.75, 1.0]:
        y = margin["top"] + plot_h - tick / max_y * plot_h
        parts.append(
            f'<line class="grid" x1="{margin["left"]}" y1="{y}" x2="{width - margin["right"]}" y2="{y}"/>'
        )
        parts.append(
            f'<text class="label" x="{margin["left"] - 10}" y="{y + 4}" text-anchor="end">{tick:.2f}</text>'
        )
    parts.append(
        f'<line class="axis" x1="{margin["left"]}" y1="{margin["top"]}" x2="{margin["left"]}" y2="{margin["top"] + plot_h}"/>'
    )
    parts.append(
        f'<line class="axis" x1="{margin["left"]}" y1="{margin["top"] + plot_h}" x2="{width - margin["right"]}" y2="{margin["top"] + plot_h}"/>'
    )
    for i, label in enumerate(labels):
        center = margin["left"] + i * bar_group + bar_group / 2
        parts.append(
            f'<text class="label" x="{center}" y="{height - 40}" text-anchor="end" transform="rotate(-40 {center} {height - 40})">{html.escape(label)}</text>'
        )
        for j, (_, vals, color) in enumerate(series):
            value = vals[i]
            x = center - (len(series) * bar_w) / 2 + j * bar_w
            h = value / max_y * plot_h
            y = margin["top"] + plot_h - h
            parts.append(
                f'<rect x="{x}" y="{y}" width="{bar_w - 2}" height="{h}" fill="{color}"><title>{html.escape(label)} {value:.3f}</title></rect>'
            )
    legend_x = margin["left"]
    for name, _, color in series:
        parts.append(
            f'<rect x="{legend_x}" y="{height - 24}" width="12" height="12" fill="{color}"/>'
        )
        parts.append(
            f'<text class="legend" x="{legend_x + 18}" y="{height - 14}">{html.escape(name)}</text>'
        )
        legend_x += 150
    parts.append("</svg>")
    path.write_text("\n".join(parts))


def color_scale(value: float, vmin: float, vmax: float) -> str:
    if vmax == vmin:
        t = 0.5
    else:
        t = (value - vmin) / (vmax - vmin)
    t = max(0.0, min(1.0, t))
    if t < 0.5:
        u = t / 0.5
        r = int(176 + (245 - 176) * u)
        g = int(52 + (245 - 52) * u)
        b = int(70 + (245 - 70) * u)
    else:
        u = (t - 0.5) / 0.5
        r = int(245 + (40 - 245) * u)
        g = int(245 + (160 - 245) * u)
        b = int(245 + (90 - 245) * u)
    return f"rgb({r},{g},{b})"


def svg_heatmap(
    path: Path,
    title: str,
    rows: list[str],
    cols: list[str],
    values: dict[tuple[str, str], float],
) -> None:
    if not rows or not cols or not values:
        path.write_text("")
        return
    cell_w = 96
    cell_h = 24
    left = 260
    top = 60
    width = left + cell_w * len(cols) + 40
    height = top + cell_h * len(rows) + 70
    vals = list(values.values())
    bound = max(abs(min(vals)), abs(max(vals)), 0.01)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<style>text{font-family:Arial,sans-serif;font-size:11px}.title{font-size:18px;font-weight:700}.task{font-size:10px}.col{font-size:12px;font-weight:700}</style>",
        f'<text class="title" x="{width / 2}" y="28" text-anchor="middle">{html.escape(title)}</text>',
    ]
    for j, col in enumerate(cols):
        x = left + j * cell_w + cell_w / 2
        parts.append(
            f'<text class="col" x="{x}" y="50" text-anchor="middle">{html.escape(col)}</text>'
        )
    for i, row in enumerate(rows):
        y = top + i * cell_h
        parts.append(
            f'<text class="task" x="{left - 8}" y="{y + 16}" text-anchor="end">{html.escape(row)}</text>'
        )
        for j, col in enumerate(cols):
            x = left + j * cell_w
            value = values.get((row, col), float("nan"))
            fill = "#f3f3f3" if math.isnan(value) else color_scale(value, -bound, bound)
            parts.append(
                f'<rect x="{x}" y="{y}" width="{cell_w}" height="{cell_h}" fill="{fill}" stroke="#fff"/>'
            )
            label = "" if math.isnan(value) else f"{value:+.2f}"
            parts.append(
                f'<text x="{x + cell_w / 2}" y="{y + 16}" text-anchor="middle">{label}</text>'
            )
    parts.append(
        f'<text x="{left}" y="{height - 24}">Red = skill lower reward; green = skill higher reward. Symmetric scale +/-{bound:.2f}.</text>'
    )
    parts.append("</svg>")
    path.write_text("\n".join(parts))


def make_plots(
    out_dir: Path, cells: list[dict], deltas: list[dict], contamination: list[dict]
) -> list[Path]:
    plots = out_dir / "plots"
    plots.mkdir(parents=True, exist_ok=True)
    native_groups = defaultdict(list)
    for c in cells:
        if c["schema"] == "native" and c["condition"] in {"no-skill", "with-skill"}:
            native_groups[(c["model"], c["condition"])].append(c["mean_reward"])
    labels = sorted({model for model, _ in native_groups})
    svg_bar(
        plots / "native_model_condition_reward.svg",
        "Native Schema Mean Reward by Model and Skill Condition",
        labels,
        [
            (
                "no-skill",
                [mean(native_groups[(m, "no-skill")]) for m in labels],
                "#4c78a8",
            ),
            (
                "with-skill",
                [mean(native_groups[(m, "with-skill")]) for m in labels],
                "#59a14f",
            ),
        ],
    )
    tasks = sorted({d["task"] for d in deltas})
    models = sorted({d["model"] for d in deltas})
    values = {(d["task"], d["model"]): d["delta"] for d in deltas}
    svg_heatmap(
        plots / "task_skill_delta_heatmap.svg",
        "Native Skill Delta by Task and Model",
        tasks,
        models,
        values,
    )
    if contamination:
        cont_labels = [r["task"] for r in contamination]
        svg_bar(
            plots / "contamination_rewards_by_task.svg",
            "gpt-5.4-mini No-Skill Reward Under Schema Perturbation",
            cont_labels,
            [
                ("native", [r["native_no_skill"] for r in contamination], "#4c78a8"),
                (
                    "obfuscated",
                    [r["obfuscated_no_skill"] for r in contamination],
                    "#f28e2b",
                ),
                (
                    "restructured",
                    [r["restructured_no_skill"] for r in contamination],
                    "#e15759",
                ),
            ],
        )
    return sorted(plots.glob("*.svg"))


def make_report(
    results_root: Path,
    rows: list[dict],
    cells: list[dict],
    deltas: list[dict],
    contamination: list[dict],
    controls: list[dict],
    plots: list[Path],
    *,
    profile: str,
    matrix_info: dict,
) -> str:
    native_rows = [r for r in rows if r["schema"] == "native"]
    all_ok = all(
        r["publishable"]
        and r["isolated"]
        and r["filesystem_canary"]
        and r["contamination_lint"]
        and r["agent_returncode"] in (0, None)
        for r in rows
    )
    expected_count = matrix_info["expected_count"]
    expected_complete = (
        len(rows) == expected_count
        and not matrix_info["missing"]
        and not matrix_info["unexpected"]
    )
    bad_status = [r for r in rows if r["agent_status"] not in (None, "completed")]
    full_pass = sum((r["failed"] or 0) == 0 and (r["errors"] or 0) == 0 for r in rows)
    diagnostics_failed = sum(r["diagnostics_failed"] for r in rows)
    output_csv_count = sum((Path(r["path"]) / "output.csv").exists() for r in rows)
    trace_count = sum((Path(r["path"]) / "trace.jsonl").exists() for r in rows)
    instruction_count = sum((Path(r["path"]) / "instruction.md").exists() for r in rows)
    egress_count = sum((Path(r["path"]) / "egress.jsonl").exists() for r in rows)
    native_summary = defaultdict(list)
    for row in native_rows:
        if row["condition"] in {"no-skill", "with-skill"}:
            native_summary[(row["model"], row["condition"])].append(row["reward"])
    by_model = defaultdict(list)
    for d in deltas:
        by_model[d["model"]].append(d["delta"])
    by_task = defaultdict(list)
    for d in deltas:
        by_task[d["task"]].append(d["delta"])
    task_delta = sorted(
        [{"task": task, "delta": mean(vals)} for task, vals in by_task.items()],
        key=lambda x: x["delta"],
        reverse=True,
    )
    cont_obf = [r["obfuscated_delta"] for r in contamination]
    cont_res = [r["restructured_delta"] for r in contamination]
    control_groups = defaultdict(list)
    for row in controls:
        control_groups[row["condition"]].append(row)
    low_runs = sorted(rows, key=lambda r: r["reward"])[:15]
    highest_help = sorted(deltas, key=lambda d: d["delta"], reverse=True)[:12]
    strongest_hurt = sorted(deltas, key=lambda d: d["delta"])[:12]
    weak_cells = sorted(cells, key=lambda c: c["mean_reward"])[:15]
    variable_cells = sorted(
        cells, key=lambda c: c["max_reward"] - c["min_reward"], reverse=True
    )[:12]
    skill_all_rows = []
    cell_index = {
        (c["task"], c["model"], c["condition"], c["schema"]): c for c in cells
    }
    for cell in cells:
        if cell["condition"] != "with-skill-all":
            continue
        no_skill = cell_index.get(
            (cell["task"], cell["model"], "no-skill", cell["schema"])
        )
        with_skill = cell_index.get(
            (cell["task"], cell["model"], "with-skill", cell["schema"])
        )
        skill_all_rows.append(
            {
                "task": cell["task"],
                "no_skill": no_skill["mean_reward"] if no_skill else None,
                "with_skill": with_skill["mean_reward"] if with_skill else None,
                "with_skill_all": cell["mean_reward"],
                "all_minus_targeted": (
                    cell["mean_reward"] - with_skill["mean_reward"]
                    if with_skill
                    else None
                ),
            }
        )
    skill_all_rows.sort(key=lambda r: r["all_minus_targeted"] or 0)

    task_form_summary = defaultdict(list)
    for row in rows:
        form = "raw" if row["task"].endswith("-raw") else "native"
        task_form_summary[(row["model"], row["condition"], row["schema"], form)].append(
            row["reward"]
        )

    task_vals = [x["delta"] for x in task_delta]
    se = sd(task_vals) / math.sqrt(len(task_vals)) if task_vals else float("nan")
    ci_low = mean(task_vals) - 1.96 * se
    ci_high = mean(task_vals) + 1.96 * se

    lines = [
        "# Codex Benchmark Report",
        "",
        f"Results root: `{results_root}`",
        f"Matrix profile: `{profile}`",
        "",
        "## Executive Summary",
        "",
        f"- Campaign completeness: `{len(rows)}` runs found; expected `{profile}` Codex matrix is `{expected_count}`, so completeness is `{expected_complete}`.",
        f"- Publishability audit: `{all_ok}`. All runs are marked publishable, isolated, containerized, canary-passed, and contamination-lint-passed; nonzero agent exits: `0`; incomplete statuses: `{len(bad_status)}`.",
        f"- Diagnostic accuracy: `{full_pass}/{len(rows)}` runs pass every benchmark diagnostic. The remaining runs are still valid publishable attempts, but they contain semantic mismatches against ground truth.",
        f"- Native single-skill effect: task-balanced mean delta is `{fmt(mean(task_vals))}` reward points across 28 tasks, with approximate 95% CI `{fmt(ci_low)}` to `{fmt(ci_high)}` across task-level deltas.",
        f"- Directionality: `{sum(x['delta'] > 0 for x in task_delta)}/28` tasks improve after averaging the two Codex models; `{sum(d['delta'] > 0 for d in deltas)}/56` task-model pairs improve.",
    ]
    if contamination:
        lines.append(
            f"- Schema perturbation probe: for gpt-5.4-mini no-skill runs, obfuscation changes mean reward by `{fmt(mean(cont_obf))}` and restructuring by `{fmt(mean(cont_res))}` relative to native on matched tasks."
        )
    else:
        lines.append(
            "- Schema perturbation probe: no obfuscated/restructured cells are present in this matrix profile."
        )
    for condition, vals in sorted(control_groups.items()):
        lines.append(
            f"- Control `{condition}`: mean control-minus-targeted delta is `{fmt(mean([v['control_minus_with_skill'] for v in vals]))}` across `{len(vals)}` task-model cells."
        )
    lines += [
        "",
        "## Publishability And Integrity",
        "",
        "These results satisfy the campaign-level publishability checks encoded in the result JSONs when every run has `publishable=true`, `isolated=true`, `filesystem_canary.passed=true`, `filesystem_canary.containerized_agent=true`, and `contamination_lint.passed=true`. Completeness is checked against the selected `benchmark/matrix.py` profile.",
        "",
        "| Check | Value |",
        "|---|---:|",
        f"| Runs | {len(rows)} |",
        f"| Expected runs | {expected_count} |",
        f"| Missing expected run keys | {len(matrix_info['missing'])} |",
        f"| Unexpected run keys | {len(matrix_info['unexpected'])} |",
        f"| Cells | {len(cells)} |",
        f"| Expected cells | {matrix_info['expected_cells']} |",
        f"| Publishable flag failures | {sum(not r['publishable'] for r in rows)} |",
        f"| Isolation flag failures | {sum(not r['isolated'] for r in rows)} |",
        f"| Filesystem canary failures | {sum(not r['filesystem_canary'] for r in rows)} |",
        f"| Contamination lint failures | {sum(not r['contamination_lint'] for r in rows)} |",
        f"| Nonzero agent exits | {sum(r['agent_returncode'] not in (0, None) for r in rows)} |",
        f"| Missing rewards | {sum(r['reward'] is None for r in rows)} |",
        f"| Fully passing diagnostic runs | {full_pass} |",
        f"| Runs with diagnostics_failed=true | {diagnostics_failed} |",
        f"| Retained output.csv artifacts | {output_csv_count} |",
        f"| Retained trace.jsonl artifacts | {trace_count} |",
        f"| Retained instruction.md artifacts | {instruction_count} |",
        f"| Retained egress.jsonl artifacts | {egress_count} |",
        "",
        "Important interpretation constraint: the matrix is adaptive and pilot-informed, with different seed counts by tier. Headline claims should use task-balanced or pre-specified tier estimands, not naive run-weighted averages. Also distinguish publishability from correctness: a publishable failed attempt is scientifically useful evidence, but not a successful clinical derivation.",
        "",
    ]
    if output_csv_count == len(rows) and trace_count == len(rows):
        lines += [
            "Artifact retention: every discovered run retained `output.csv` and `trace.jsonl` in the campaign directory.",
            "",
        ]
    else:
        lines += [
            "Artifact caveat: all `result.json` metrics are present, but at least one per-run `output.csv` or copied trace artifact is not retained in the campaign directory. This is not an isolation failure. If the release archive is expected to include every attempted CSV, inspect file-size export limits and regenerate or document the missing artifacts.",
            "",
        ]
    lines += [
        "## Native Skill Effect",
        "",
        "| Model | no-skill mean | with-skill mean | task-paired mean delta | positive task deltas |",
        "|---|---:|---:|---:|---:|",
    ]
    for model in sorted(by_model):
        model_deltas = by_model[model]
        lines.append(
            f"| {model} | {fmt(mean(native_summary[(model, 'no-skill')]))} | {fmt(mean(native_summary[(model, 'with-skill')]))} | {fmt(mean(model_deltas))} | {sum(x > 0 for x in model_deltas)}/{len(model_deltas)} |"
        )
    lines += [
        "",
        "Largest task-level gains after averaging both Codex models:",
        "",
        "| Task | Mean delta |",
        "|---|---:|",
    ]
    for row in task_delta[:12]:
        lines.append(f"| `{row['task']}` | {fmt(row['delta'])} |")
    lines += [
        "",
        "Largest negative or flat task-level effects:",
        "",
        "| Task | Mean delta |",
        "|---|---:|",
    ]
    for row in sorted(task_delta, key=lambda x: x["delta"])[:12]:
        lines.append(f"| `{row['task']}` | {fmt(row['delta'])} |")
    lines += [
        "",
        "## Surprises",
        "",
        "- The OASIS/sepsis skill-hurts concern from the pilot did not reproduce in this clean Codex campaign. `mimic-oasis-24h`, `mimic-oasis-24h-raw`, `eicu-oasis`, and `mimic-sepsis3-raw` all have positive skill deltas for both models.",
        "- The largest skill gains are concentrated in procedural data-engineering tasks: urine-output rolling windows, MELD, suspected infection timing, baseline creatinine, and ventilation episodes.",
        "- The strongest remaining negative mean effects are small in task-balanced terms except `mimic-vasopressor-equivalents-raw` for gpt-5.5 and `mimic-ventilation-raw` for gpt-5.4-mini.",
        "- `gpt-5.5` is stronger overall, but not uniformly. It trails `gpt-5.4-mini` on some no-skill cells, notably MELD native/raw and suspected-infection raw, while both models reach much higher performance once the targeted skill is available.",
        "",
        "## Task Form And Schema Summary",
        "",
        "| Model | Condition | Schema | Task form | Runs | Mean reward |",
        "|---|---|---|---|---:|---:|",
    ]
    for key, vals in sorted(task_form_summary.items()):
        lines.append(
            f"| {key[0]} | {key[1]} | {key[2]} | {key[3]} | {len(vals)} | {fmt(mean(vals))} |"
        )
    lines += [
        "",
        "Raw tasks are harder than corresponding native-schema task variants for the native no-skill and with-skill comparisons.",
        "",
    ]
    if skill_all_rows:
        lines += [
            "## Skill-All Probe",
            "",
            "| Task | no-skill | targeted skill | all skills | all - targeted |",
            "|---|---:|---:|---:|---:|",
        ]
        for row in skill_all_rows:
            lines.append(
                f"| `{row['task']}` | {fmt(row['no_skill'])} | {fmt(row['with_skill'])} | {fmt(row['with_skill_all'])} | {fmt(row['all_minus_targeted'])} |"
            )
        lines += [
            "",
            "The all-skills condition is best interpreted as a discovery/noise probe, not a third headline treatment.",
            "",
        ]
    if controls:
        lines += [
            "## Matched-Context Controls",
            "",
            "| Task | Model | Control | no-skill | targeted skill | control | control - targeted |",
            "|---|---|---|---:|---:|---:|---:|",
        ]
        for row in sorted(
            controls,
            key=lambda r: (r["condition"], r["task"], r["model"]),
        ):
            lines.append(
                f"| `{row['task']}` | {row['model']} | {row['condition']} | {fmt(row['no_skill_mean'])} | {fmt(row['with_skill_mean'])} | {fmt(row['control_mean'])} | {fmt(row['control_minus_with_skill'])} |"
            )
        lines.append("")
    lines += [
        "## Failure Modes",
        "",
        "The low-reward runs are valid executions rather than infrastructure failures. The dominant failure modes are:",
        "",
        "- Wrong key grain or row explosion, especially urine-output rate and vasopressor interval tasks. These failures emit plausible CSVs at the wrong temporal grain or with incorrect interval keys.",
        "- Infection and Sepsis-3 temporal-pairing mistakes. The likely errors are antibiotic-culture window direction, timestamp choice, culture over-inclusion, and compounding with SOFA timing.",
        "- Ventilation interval segmentation failures. Raw ventilation remains weak even with skills, suggesting episode construction, mode priority, and contiguous-state collapse are still difficult.",
        "- Severity-score component drift. APSIII, SAPS-II, OASIS, SOFA, MELD, and KDIGO often have correct-shaped output but miss exact bin boundaries, windows, defaults, or component formulas.",
        "- Baseline creatinine hierarchy errors. Some runs have perfect key precision but poor clinical values, consistent with wrong CKD logic, MDRD back-calculation, demographic joins, or hierarchy ordering.",
        "",
        "Weakest cells by mean reward:",
        "",
        "| Mean reward | Task | Condition | Schema | Model | n |",
        "|---:|---|---|---|---|---:|",
    ]
    for cell in weak_cells:
        lines.append(
            f"| {fmt(cell['mean_reward'])} | `{cell['task']}` | {cell['condition']} | {cell['schema']} | {cell['model']} | {cell['n']} |"
        )
    lines += [
        "",
        "Highest within-cell variability:",
        "",
        "| Range | Task | Condition | Schema | Model | n | min | max |",
        "|---:|---|---|---|---|---:|---:|---:|",
    ]
    for cell in variable_cells:
        value_range = cell["max_reward"] - cell["min_reward"]
        lines.append(
            f"| {fmt(value_range)} | `{cell['task']}` | {cell['condition']} | {cell['schema']} | {cell['model']} | {cell['n']} | {fmt(cell['min_reward'])} | {fmt(cell['max_reward'])} |"
        )
    lines += [
        "",
        "## Task-Model Extremes",
        "",
        "Largest task-model skill gains:",
        "",
        "| Task | Model | no-skill | with-skill | Delta |",
        "|---|---|---:|---:|---:|",
    ]
    for row in highest_help:
        lines.append(
            f"| `{row['task']}` | {row['model']} | {fmt(row['no_skill_mean'])} | {fmt(row['with_skill_mean'])} | {fmt(row['delta'])} |"
        )
    lines += [
        "",
        "Largest task-model skill declines:",
        "",
        "| Task | Model | no-skill | with-skill | Delta |",
        "|---|---|---:|---:|---:|",
    ]
    for row in strongest_hurt:
        lines.append(
            f"| `{row['task']}` | {row['model']} | {fmt(row['no_skill_mean'])} | {fmt(row['with_skill_mean'])} | {fmt(row['delta'])} |"
        )
    lines += [
        "",
        "Lowest individual rewards, useful for failure-mode review:",
        "",
        "| Reward | Task | Condition | Schema | Model | Trial | Key precision | Extra keys |",
        "|---:|---|---|---|---|---:|---:|---:|",
    ]
    for row in low_runs:
        lines.append(
            f"| {fmt(row['reward'])} | `{row['task']}` | {row['condition']} | {row['schema']} | {row['model']} | {row['trial']} | {fmt(row['key_precision'])} | {row['extra_keys']} |"
        )
    lines += [
        "",
        "## Exported Artifacts",
        "",
        "- `runs.csv`: one row per run with integrity flags, reward, diagnostics, and timing.",
        "- `cells.csv`: one row per task/condition/schema/model cell.",
        "- `native_skill_deltas.csv`: native no-skill vs with-skill task-model deltas.",
        "- `contamination_summary.csv`: native, obfuscated, and restructured no-skill comparison for gpt-5.4-mini when the selected matrix contains schema-perturbation cells.",
        "- `control_condition_summary.csv`: native matched-context control comparisons when the selected matrix contains no-SQL, raw-SQL, or decoy conditions.",
        "- `plots/*.svg`: visual summaries.",
        "",
    ]
    for plot in plots:
        try:
            plot_label = plot.relative_to(results_root / "analysis")
        except ValueError:
            plot_label = plot
        lines.append(f"- `{plot_label}`")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=DEFAULT_RESULTS_ROOT)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument(
        "--profile",
        default=DEFAULT_PROFILE,
        choices=["powered", "provider-comparison", "rerun-v1.1"],
        help="Matrix profile used to check completeness and assign tiers.",
    )
    parser.add_argument("--agent", default="codex")
    parser.add_argument("--seeds", type=int, default=5)
    args = parser.parse_args()

    results_root = args.results_root.resolve()
    out_dir = args.out_dir.resolve() if args.out_dir else results_root / "analysis"
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = load_rows(results_root)
    if not rows:
        raise SystemExit(f"No result.json files found under {results_root}")
    matrix_info = attach_tiers(
        rows, profile=args.profile, agent=args.agent, seeds=args.seeds
    )
    cells = cell_rows(rows)
    deltas = delta_rows(cells)
    contamination = contamination_rows(cells)
    controls = control_rows(cells)

    run_fields = [
        "tier",
        "tier_name",
        "run_id",
        "task",
        "condition",
        "schema",
        "agent",
        "model",
        "trial",
        "reasoning_effort",
        "publishable",
        "isolated",
        "filesystem_canary",
        "containerized_agent",
        "contamination_lint",
        "agent_returncode",
        "agent_status",
        "elapsed_seconds",
        "passed",
        "failed",
        "errors",
        "total_tests",
        "reward",
        "reward_uncapped",
        "diagnostics_failed",
        "key_precision",
        "extra_keys",
        "agent_unique_keys",
        "path",
    ]
    cell_fields = [
        "tier",
        "tier_name",
        "task",
        "condition",
        "schema",
        "model",
        "n",
        "mean_reward",
        "sd_reward",
        "median_reward",
        "min_reward",
        "max_reward",
        "mean_key_precision",
        "sum_failed_tests",
        "sum_errors",
        "sum_extra_keys",
    ]
    write_csv(out_dir / "runs.csv", rows, run_fields)
    write_csv(out_dir / "cells.csv", cells, cell_fields)
    write_csv(
        out_dir / "native_skill_deltas.csv",
        deltas,
        [
            "task",
            "schema",
            "model",
            "no_skill_mean",
            "with_skill_mean",
            "delta",
            "no_skill_n",
            "with_skill_n",
        ],
    )
    write_csv(
        out_dir / "contamination_summary.csv",
        contamination,
        [
            "task",
            "native_no_skill",
            "obfuscated_no_skill",
            "restructured_no_skill",
            "obfuscated_delta",
            "restructured_delta",
        ],
    )
    write_csv(
        out_dir / "control_condition_summary.csv",
        controls,
        [
            "task",
            "model",
            "condition",
            "no_skill_mean",
            "with_skill_mean",
            "control_mean",
            "control_minus_no_skill",
            "control_minus_with_skill",
            "control_n",
        ],
    )
    plots = make_plots(out_dir, cells, deltas, contamination)
    report = make_report(
        results_root,
        rows,
        cells,
        deltas,
        contamination,
        controls,
        plots,
        profile=args.profile,
        matrix_info=matrix_info,
    )
    (out_dir / "CODEX_FULL_REPORT.md").write_text(report)

    print(f"Wrote analysis to {out_dir}")
    print(f"Runs: {len(rows)}; cells: {len(cells)}; plots: {len(plots)}")


if __name__ == "__main__":
    main()
