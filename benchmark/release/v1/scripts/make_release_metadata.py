#!/usr/bin/env python3
"""Generate paper metadata tables from benchmark specs and release artifacts."""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

import tomllib

M4_DIR = Path(
    os.environ.get("M4BENCH_M4_DIR", Path(__file__).resolve().parents[4])
).resolve()
PAPER_DIR = Path(
    os.environ.get("M4BENCH_PAPER_DIR", Path(__file__).resolve().parents[1])
).resolve()
BENCHMARK_DIR = M4_DIR / "benchmark"
TASKS_DIR = BENCHMARK_DIR / "tasks"
GROUND_TRUTH_DIR = BENCHMARK_DIR / "ground_truth"
RESULTS_DIR = Path(
    os.environ.get("M4BENCH_RESULTS_DIR", BENCHMARK_DIR / "results")
).resolve()
TABLE_DIR = PAPER_DIR / "tables"
PLANNING_DIR = PAPER_DIR / "planning"

CODEX_RELEASE = RESULTS_DIR / "release-20260502-codex-v11"
CODEX_RERUN = RESULTS_DIR / "review-rerun-20260504-codex"
CLAUDE_RELEASE = RESULTS_DIR / "release-20260502-claude-provider"
CLAUDE_RERUN = RESULTS_DIR / "review-rerun-20260504-claude"
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

EXPECTED_ARTIFACTS = [
    "result.json",
    "output.csv",
    "instruction.md",
    "trace.jsonl",
    "egress.jsonl",
]
HARDWARE = "MacBook Pro, Apple M3 Pro, 18 GB memory"
PROVENANCE_ONLY_DIRS = {
    "Codex primary": 40,
    "Claude sentinel": 0,
}


sys.path.insert(0, str(BENCHMARK_DIR))
from lib.db import _task_key  # noqa: E402
from report_results import load_rows  # noqa: E402


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
    path: Path, headers: list[str], rows: list[list[object]], align: str
) -> None:
    lines = [rf"\begin{{tabular}}{{{align}}}", r"\toprule"]
    lines.append(" & ".join(latex_escape(h) for h in headers) + r" \\")
    lines.append(r"\midrule")
    for row in rows:
        lines.append(" & ".join(latex_escape(cell) for cell in row) + r" \\")
    lines.extend([r"\bottomrule", r"\end{tabular}", ""])
    path.write_text("\n".join(lines))


def run_key(row: dict) -> tuple[str, str, str, str, int]:
    return (
        row["task"],
        row["condition"],
        row["schema"],
        row["model"],
        int(row["trial"]),
    )


def combine_rows(release_root: Path, rerun_root: Path) -> list[dict]:
    rows = {run_key(row): row for row in load_rows(release_root)}
    for row in load_rows(rerun_root):
        rows[run_key(row)] = row
    return list(rows.values())


def filter_claude_paper_rows(rows: list[dict]) -> list[dict]:
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


def count_csv_rows(path: Path) -> int:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", newline="") as handle:
        return max(sum(1 for _ in handle) - 1, 0)


def truth_rows_for_task(task_name: str) -> int:
    key = _task_key(task_name)
    for suffix in (".csv.gz", ".csv"):
        path = GROUND_TRUTH_DIR / f"{key}{suffix}"
        if path.exists():
            return count_csv_rows(path)
    raise FileNotFoundError(f"No ground-truth CSV found for {task_name} ({key})")


def family_label(family: str) -> str:
    labels = {
        "apsiii": "APS III",
        "charlson": "Charlson",
        "creatinine-baseline": "Baseline creatinine",
        "gcs": "GCS",
        "kdigo": "KDIGO AKI",
        "meld": "MELD",
        "oasis": "OASIS",
        "sapsii": "SAPS-II",
        "sepsis3": "Sepsis-3",
        "sirs": "SIRS",
        "sofa": "SOFA",
        "suspicion-infection": "Suspected infection",
        "urine-output-rate": "Urine-output rate",
        "vasopressor-equivalents": "Vasopressor equivalents",
        "ventilation": "Ventilation",
    }
    return labels.get(family, family)


def key_grain(key_columns: list[str]) -> str:
    keys = set(key_columns)
    if "ventilation_seq" in keys or "starttime" in keys or "endtime" in keys:
        return "interval"
    if "window_start" in keys or "window_end" in keys or "charttime" in keys:
        return "stay-window"
    if "ab_id" in keys or "suspected_infection_time" in keys or "sofa_time" in keys:
        return "event"
    if keys == {"stay_id"} or "stay_id" in keys:
        return "stay"
    if "patientunitstayid" in keys:
        return "stay"
    if "hadm_id" in keys:
        return "admission"
    return "/".join(key_columns)


def database_label(raw: str) -> str:
    return {"mimic-iv": "MIMIC-IV", "eicu": "eICU"}.get(raw, raw)


def task_details() -> list[dict]:
    rows = []
    for task_file in sorted(TASKS_DIR.glob("*/*/task.toml")):
        with task_file.open("rb") as handle:
            config = tomllib.load(handle)
        metadata = config["metadata"]
        evaluation = config["evaluation"]
        name = metadata["name"]
        rows.append(
            {
                "family": task_file.parents[1].name,
                "task": name,
                "mode": metadata.get("mode", "standard"),
                "database": database_label(
                    metadata.get(
                        "database", config.get("database", {}).get("source", "mimic-iv")
                    )
                ),
                "key_grain": key_grain(evaluation["key_columns"]),
                "scored_columns": len(evaluation["value_columns"]),
                "truth_rows": truth_rows_for_task(name),
            }
        )
    return sorted(rows, key=lambda row: row["task"])


def write_task_tables(rows: list[dict]) -> None:
    write_table(
        TABLE_DIR / "task_details.tex",
        ["Task", "Mode", "Database", "Key grain", "Scored columns", "Truth rows"],
        [
            [
                row["task"],
                row["mode"],
                row["database"],
                row["key_grain"],
                row["scored_columns"],
                row["truth_rows"],
            ]
            for row in rows
        ],
        "llllrr",
    )

    by_family: dict[str, dict] = {}
    for row in rows:
        info = by_family.setdefault(
            row["family"],
            {"tasks": 0, "standard": 0, "raw": 0, "databases": set()},
        )
        info["tasks"] += 1
        info[row["mode"]] += 1
        info["databases"].add(row["database"])
    inventory_rows = []
    for family in sorted(by_family):
        info = by_family[family]
        inventory_rows.append(
            [
                family_label(family),
                info["tasks"],
                info["standard"],
                info["raw"],
                "/".join(sorted(info["databases"])),
            ]
        )
    inventory_rows.append(
        [
            "Total",
            sum(row[1] for row in inventory_rows),
            sum(row[2] for row in inventory_rows),
            sum(row[3] for row in inventory_rows),
            "MIMIC-IV/eICU",
        ]
    )
    lines = [
        r"\begin{tabular}{lrrrr}",
        r"\toprule",
        r"Family & Tasks & Standard & Raw & Database \\",
        r"\midrule",
    ]
    for index, row in enumerate(inventory_rows):
        if row[0] == "Total":
            lines.append(r"\midrule")
        lines.append(" & ".join(latex_escape(cell) for cell in row) + r" \\")
    lines.extend([r"\bottomrule", r"\end{tabular}", ""])
    (TABLE_DIR / "task_inventory.tex").write_text("\n".join(lines))


def result_json(path: Path) -> dict:
    with (path / "result.json").open() as handle:
        return json.load(handle)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def human_bytes(size: int) -> str:
    if size <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    power = min(int(math.log(size, 1024)), len(units) - 1)
    value = size / (1024**power)
    return f"{value:.1f} {units[power]}"


def du_bytes(paths: list[Path]) -> int:
    total = 0
    for path in paths:
        if not path.exists():
            continue
        proc = subprocess.run(
            ["du", "-sk", str(path)], check=True, capture_output=True, text=True
        )
        total += int(proc.stdout.split()[0]) * 1024
    return total


def campaign_summary(label: str, rows: list[dict], source_roots: list[Path]) -> dict:
    artifact_counts = Counter()
    artifact_bytes = 0
    elapsed = 0.0
    input_tokens = cached_input_tokens = output_tokens = 0
    hash_entries = []

    selected_run_dirs = []
    for row in rows:
        run_path = Path(row["path"])
        selected_run_dirs.append(run_path)
        data = result_json(run_path)
        elapsed += float(
            data.get("agent_result", {}).get("elapsed_seconds")
            or row.get("elapsed_seconds")
            or 0.0
        )
        usage = data.get("token_usage", {})
        input_tokens += int(usage.get("input_tokens") or 0)
        cached_input_tokens += int(usage.get("cached_input_tokens") or 0)
        output_tokens += int(usage.get("output_tokens") or 0)
        for name in EXPECTED_ARTIFACTS:
            artifact = run_path / name
            if artifact.exists():
                artifact_counts[name] += 1
                artifact_bytes += artifact.stat().st_size
                hash_entries.append(
                    {
                        "campaign": label,
                        "run_id": row["run_id"],
                        "artifact": name,
                        "relative_path": str(artifact.relative_to(RESULTS_DIR)),
                        "size_bytes": artifact.stat().st_size,
                        "sha256": sha256_file(artifact),
                    }
                )

    retained_dirs = len(rows)
    provenance_only_dirs = PROVENANCE_ONLY_DIRS.get(label, 0)
    canonical_runs = retained_dirs - provenance_only_dirs

    return {
        "label": label,
        "runs": canonical_runs,
        "canonical_runs": canonical_runs,
        "provenance_only_dirs": provenance_only_dirs,
        "retained_dirs": retained_dirs,
        "source_roots": [root.name for root in source_roots],
        "source_root_bytes": du_bytes(selected_run_dirs),
        "artifact_bytes": artifact_bytes,
        "elapsed_seconds": elapsed,
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "output_tokens": output_tokens,
        "artifact_counts": dict(artifact_counts),
        "hash_entries": hash_entries,
    }


def compact_int(value: int) -> str:
    return f"{value:,}"


def hours(seconds: float) -> str:
    return f"{seconds / 3600:.1f}"


def write_release_tables(campaigns: list[dict]) -> None:
    write_table(
        TABLE_DIR / "artifact_package.tex",
        [
            "Campaign",
            "Canonical runs",
            "Provenance-only dirs",
            "Retained dirs",
            "result.json",
            "output.csv",
            "instruction.md",
            "trace.jsonl",
            "egress.jsonl",
            "Retained size",
        ],
        [
            [
                campaign["label"],
                campaign["canonical_runs"],
                campaign["provenance_only_dirs"],
                campaign["retained_dirs"],
                campaign["artifact_counts"].get("result.json", 0),
                campaign["artifact_counts"].get("output.csv", 0),
                campaign["artifact_counts"].get("instruction.md", 0),
                campaign["artifact_counts"].get("trace.jsonl", 0),
                campaign["artifact_counts"].get("egress.jsonl", 0),
                human_bytes(campaign["artifact_bytes"]),
            ]
            for campaign in campaigns
        ],
        "lrrrrrrrrr",
    )

    write_table(
        TABLE_DIR / "compute_resources.tex",
        [
            "Campaign",
            "Canonical runs",
            "Provenance-only dirs",
            "Retained dirs",
            "Hardware",
            "Agent wall-clock h",
            "Uncached input",
            "Cached input",
            "Output tokens",
            "Selected dirs",
        ],
        [
            [
                campaign["label"],
                campaign["canonical_runs"],
                campaign["provenance_only_dirs"],
                campaign["retained_dirs"],
                HARDWARE,
                hours(campaign["elapsed_seconds"]),
                compact_int(campaign["input_tokens"]),
                compact_int(campaign["cached_input_tokens"]),
                compact_int(campaign["output_tokens"]),
                human_bytes(campaign["source_root_bytes"]),
            ]
            for campaign in campaigns
        ],
        "lrrrlrrrrl",
    )

    license_rows = [
        [
            "M4Bench code, tasks, evaluator, skills",
            "Benchmark artifact",
            "MIT license in the public release; anonymous review copy suppresses author-identifying metadata.",
        ],
        [
            "MIMIC-IV v3.1",
            "Source EHR data for 26 tasks",
            "PhysioNet credentialed access and MIMIC-IV data-use terms; derived databases are not openly redistributed.",
        ],
        [
            "eICU Collaborative Research Database v2",
            "Source EHR data for 2 tasks",
            "PhysioNet credentialed access and eICU data-use terms; derived databases are not openly redistributed.",
        ],
        [
            "MIT-LCP MIMIC-Code / eICU concept conventions",
            "Reference SQL lineage and procedural conventions",
            "Credited and cited; adapted SQL/procedural conventions retained with provenance.",
        ],
        [
            "Paper-facing run artifacts",
            "Audit outputs, traces, and diagnostics",
            "Released through the anonymous review package subject to source-data data-use restrictions.",
        ],
    ]
    lines = [
        r"\begin{tabular}{p{0.24\textwidth}p{0.24\textwidth}p{0.44\textwidth}}",
        r"\toprule",
    ]
    lines.append(r"Asset & Role & Access, license, or terms \\")
    lines.append(r"\midrule")
    for row in license_rows:
        lines.append(" & ".join(latex_escape(cell) for cell in row) + r" \\")
    lines.extend([r"\bottomrule", r"\end{tabular}", ""])
    (TABLE_DIR / "asset_licenses.tex").write_text("\n".join(lines))


def write_clinical_reference_audit() -> None:
    rows = [
        [
            "Suspected infection / Sepsis-3",
            "Antibiotic--microbiology timing rule from public concept code",
            "Broad culture inclusion can overcall suspected infection; downstream Sepsis-3 inherits this target.",
        ],
        [
            "SOFA / Sepsis-3",
            "Missing organ components default to zero",
            "Agreement may reflect the public-code missingness convention rather than adjudicated organ failure.",
        ],
        [
            "APS III",
            "MIMIC-Code component implementation",
            "Known respiratory and oxygenation pathway discrepancies are retained for reproducibility.",
        ],
        [
            "Vasopressor equivalents",
            "Five-agent norepinephrine-equivalent mapping",
            "Angiotensin II administrations are not scored in the current reference.",
        ],
        [
            "eICU OASIS",
            "eICU APACHE abstraction tables where source charting is not equivalent",
            "eICU raw tasks are not schema-symmetric with MIMIC raw reconstruction.",
        ],
    ]
    lines = [
        r"\begin{tabular}{p{0.20\textwidth}p{0.34\textwidth}p{0.38\textwidth}}",
        r"\toprule",
        r"Family & Reference convention retained & Validity caveat \\",
        r"\midrule",
    ]
    for row in rows:
        lines.append(" & ".join(latex_escape(cell) for cell in row) + r" \\")
    lines.extend([r"\bottomrule", r"\end{tabular}", ""])
    (TABLE_DIR / "clinical_reference_audit.tex").write_text("\n".join(lines))


def write_manifests(campaigns: list[dict]) -> None:
    manifest_entries = []
    summary_entries = []
    for campaign in campaigns:
        manifest_entries.extend(campaign.pop("hash_entries"))
        summary_entries.append(campaign)
    (PLANNING_DIR / "artifact_hash_manifest.json").write_text(
        json.dumps(manifest_entries, indent=2)
    )
    (PLANNING_DIR / "release_metadata_summary.json").write_text(
        json.dumps(summary_entries, indent=2)
    )

    lines = [
        "# Release Metadata Summary",
        "",
        "Generated by `benchmark/release/v1/scripts/make_release_metadata.py` from local benchmark specs and paper-facing result roots.",
        "",
        "| Campaign | Canonical runs | Provenance-only dirs | Retained dirs | Retained artifacts | Retained size | Agent wall-clock h | Input tokens | Output tokens | Selected dirs |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for campaign in summary_entries:
        retained = sum(campaign["artifact_counts"].values())
        lines.append(
            f"| {campaign['label']} | {campaign['canonical_runs']} | {campaign['provenance_only_dirs']} | "
            f"{campaign['retained_dirs']} | {retained} | {human_bytes(campaign['artifact_bytes'])} | "
            f"{hours(campaign['elapsed_seconds'])} | {compact_int(campaign['input_tokens'])} | "
            f"{compact_int(campaign['output_tokens'])} | {human_bytes(campaign['source_root_bytes'])} |"
        )
    lines += [
        "",
        f"Hash manifest entries: {len(manifest_entries)} in `planning/artifact_hash_manifest.json`.",
        "",
    ]
    (PLANNING_DIR / "release_metadata_summary.md").write_text("\n".join(lines))


def main() -> None:
    TABLE_DIR.mkdir(exist_ok=True)
    PLANNING_DIR.mkdir(exist_ok=True)

    task_rows = task_details()
    write_task_tables(task_rows)
    write_clinical_reference_audit()

    codex_rows = combine_rows(CODEX_RELEASE, CODEX_RERUN)
    claude_rows = filter_claude_paper_rows(combine_rows(CLAUDE_RELEASE, CLAUDE_RERUN))
    campaigns = [
        campaign_summary("Codex primary", codex_rows, [CODEX_RELEASE, CODEX_RERUN]),
        campaign_summary(
            "Claude sentinel", claude_rows, [CLAUDE_RELEASE, CLAUDE_RERUN]
        ),
    ]
    write_release_tables(campaigns)
    write_manifests(campaigns)
    print("Wrote task metadata, artifact, compute, license, and manifest outputs.")


if __name__ == "__main__":
    main()
