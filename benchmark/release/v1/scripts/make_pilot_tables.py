#!/usr/bin/env python3
"""Generate first-draft manuscript tables.

The pilot tables intentionally label the current Codex campaign as non-final.
They are useful for drafting the paper shape, but final manuscript tables
should point this script at a clean rerun result root or replace it with a
final-campaign generator.
"""

from __future__ import annotations

import json
import os
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import tomllib

M4_DIR = Path(
    os.environ.get("M4BENCH_M4_DIR", Path(__file__).resolve().parents[4])
).resolve()
PAPER_DIR = Path(
    os.environ.get("M4BENCH_PAPER_DIR", Path(__file__).resolve().parents[1])
).resolve()
BENCHMARK_DIR = M4_DIR / "benchmark"
TASK_DIR = BENCHMARK_DIR / "tasks"
RESULT_ROOT = BENCHMARK_DIR / "results" / "paper-20260424-2321-codex-tier1-clean"
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


def write_table(
    path: Path, headers: list[str], rows: list[list[object]], align: str | None = None
) -> None:
    align = align or ("l" * len(headers))
    lines = [rf"\begin{{tabular}}{{{align}}}", r"\toprule"]
    lines.append(" & ".join(latex_escape(h) for h in headers) + r" \\")
    lines.append(r"\midrule")
    for row in rows:
        lines.append(" & ".join(latex_escape(cell) for cell in row) + r" \\")
    lines.extend([r"\bottomrule", r"\end{tabular}", ""])
    path.write_text("\n".join(lines))


def generate_task_inventory() -> None:
    family_counts: dict[str, Counter[str]] = defaultdict(Counter)
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


def load_results() -> list[dict]:
    results = []
    if not RESULT_ROOT.exists():
        return results
    for result_file in sorted(RESULT_ROOT.rglob("result.json")):
        try:
            data = json.loads(result_file.read_text())
        except json.JSONDecodeError:
            continue
        trace_file = result_file.parent / "trace.jsonl"
        trace_text = ""
        if trace_file.exists():
            trace_text = trace_file.read_text(errors="replace")
        data["_path"] = str(result_file)
        data["_payload"] = (
            json.dumps(data, sort_keys=True) + "\n" + trace_text
        ).lower()
        results.append(data)
    return results


def mentions_ground_truth(result: dict) -> bool:
    payload = result.get("_payload", "")
    return any(
        pattern in payload
        for pattern in (
            "/benchmark/ground_truth",
            "benchmark/ground_truth",
            "ground_truth/",
        )
    )


def reward(result: dict) -> float:
    return float(result.get("test_results", {}).get("reward", 0.0))


def generate_pilot_audit(results: list[dict]) -> None:
    counts = Counter()
    for result in results:
        counts["result.json files"] += 1
        counts[f"condition:{result.get('condition', 'unknown')}"] += 1
        counts[f"schema:{result.get('schema', 'native')}"] += 1
        counts[f"model:{result.get('model', 'unknown')}"] += 1
        if result.get("publishable"):
            counts["runs marked publishable"] += 1
        if mentions_ground_truth(result):
            counts["runs mentioning ground truth or answer copying"] += 1

    rows = [
        ["Result files", counts["result.json files"]],
        ["Native-schema runs", counts["schema:native"]],
        ["Obfuscated-schema runs", counts["schema:obfuscated"]],
        ["Restructured-schema runs", counts["schema:restructured"]],
        ["No-skill runs", counts["condition:no-skill"]],
        ["With-skill runs", counts["condition:with-skill"]],
        ["With-skill-all runs", counts["condition:with-skill-all"]],
        ["Runs marked publishable", counts["runs marked publishable"]],
        [
            "Runs mentioning ground truth or answer copying",
            counts["runs mentioning ground truth or answer copying"],
        ],
    ]
    write_table(TABLE_DIR / "pilot_audit.tex", ["Quantity", "Count"], rows, align="lr")


def generate_condition_summary(results: list[dict]) -> None:
    groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    perfect: Counter[tuple[str, str]] = Counter()
    for result in results:
        if result.get("schema", "native") != "native":
            continue
        if mentions_ground_truth(result):
            continue
        key = (result.get("condition", "unknown"), result.get("model", "unknown"))
        value = reward(result)
        groups[key].append(value)
        if value == 1.0:
            perfect[key] += 1

    order = [
        ("no-skill", "gpt-5.4-mini"),
        ("with-skill", "gpt-5.4-mini"),
        ("no-skill", "gpt-5.5"),
        ("with-skill", "gpt-5.5"),
        ("with-skill-all", "gpt-5.5"),
    ]
    rows = []
    for key in order:
        values = groups.get(key, [])
        if not values:
            continue
        rows.append(
            [
                key[0],
                key[1],
                len(values),
                f"{statistics.mean(values):.3f}",
                perfect[key],
            ]
        )
    write_table(
        TABLE_DIR / "pilot_condition_summary.tex",
        ["Condition", "Model", "Runs", "Mean reward", "Perfect rewards"],
        rows,
        align="llrrr",
    )


def generate_skill_wins(results: list[dict]) -> None:
    values: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    for result in results:
        if result.get("schema", "native") != "native":
            continue
        if mentions_ground_truth(result):
            continue
        condition = result.get("condition")
        if condition not in {"no-skill", "with-skill"}:
            continue
        key = (result.get("model", "unknown"), result.get("task", "unknown"), condition)
        values[key].append(reward(result))

    rows = []
    for model in ("gpt-5.4-mini", "gpt-5.5"):
        wins = []
        tasks = {task for m, task, _ in values if m == model}
        for task in tasks:
            no_skill = values.get((model, task, "no-skill"), [])
            with_skill = values.get((model, task, "with-skill"), [])
            if not no_skill or not with_skill:
                continue
            no_mean = statistics.mean(no_skill)
            skill_mean = statistics.mean(with_skill)
            wins.append((skill_mean - no_mean, task, no_mean, skill_mean))
        for delta, task, no_mean, skill_mean in sorted(wins, reverse=True)[:5]:
            rows.append(
                [model, task, f"{no_mean:.3f}", f"{skill_mean:.3f}", f"{delta:+.3f}"]
            )

    write_table(
        TABLE_DIR / "pilot_skill_wins.tex",
        ["Model", "Task", "No skill", "With skill", "Delta"],
        rows,
        align="llrrr",
    )


def main() -> None:
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    generate_task_inventory()
    results = load_results()
    generate_pilot_audit(results)
    generate_condition_summary(results)
    generate_skill_wins(results)


if __name__ == "__main__":
    main()
