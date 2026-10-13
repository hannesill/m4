#!/usr/bin/env python3
"""Verify an extracted open evidence package and regenerate tables from it.

1. Every entry in `metadata/public_artifact_manifest.json` must exist with the
   recorded SHA-256 and size, and no unlisted file may be present.
2. Tables are regenerated from the package alone into a temporary directory and
   compared byte-for-byte with the tracked tables in this release tree:
   * claude28: `make_claude28_tables.py --evidence-dir` (stdlib only);
   * historical: `make_final_results.py` and `make_followup_tables.py` in
     frozen-reference mode (reference row counts from `task_details.tex`,
     ordered-value nMAE from the tracked cache), which needs duckdb and the
     benchmark package from this checkout.

Tables that depend on evidence outside the package are reported, not hidden.
"""

from __future__ import annotations

import argparse
import filecmp
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
RELEASE_DIR = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
from archive_io import sha256_file  # noqa: E402

UNLISTED_OK = {
    "README.md",
    "metadata/public_artifact_manifest.json",
    "metadata/SANITIZATION_REPORT.json",
    "metadata/historical_result_json_repair_lineage.json",
}
HISTORICAL_TABLES = {
    "make_final_results.py": [
        "codex_native_skill_effect.tex",
        "codex_family_sensitivity.tex",
        "codex_mode_skill_effect.tex",
        "codex_skill_gains.tex",
        "codex_skill_declines.tex",
        "codex_secondary_diagnostics_by_task.tex",
        "codex_key_precision.tex",
        "codex_matched_controls.tex",
        "codex_integrity.tex",
        "claude_native_skill_effect.tex",
        "claude_task_deltas.tex",
        "oss_native_skill_effect.tex",
        "oss_task_deltas.tex",
        "oss_schema_probe.tex",
        "oss_integrity.tex",
    ],
    "make_followup_tables.py": [
        "codex_followup_integrity.tex",
        "codex_operational_spec_by_task.tex",
        "codex_operational_spec_control.tex",
        "codex_schema_skill_generalization.tex",
    ],
}
OUTSIDE_PACKAGE = {
    "codex_schema_skill_generalization.tex": (
        "transformed-schema no-skill cells come from the April campaign root "
        "codex-full-20260428, which is not part of the retained evidence packages"
    ),
}


def package_root(path: Path) -> Path:
    if (path / "metadata" / "public_artifact_manifest.json").is_file():
        return path
    candidates = [
        p
        for p in path.iterdir()
        if (p / "metadata" / "public_artifact_manifest.json").is_file()
    ]
    if len(candidates) != 1:
        raise SystemExit(f"No single evidence package found under {path}")
    return candidates[0]


def verify_hashes(root: Path) -> int:
    manifest = json.loads(
        (root / "metadata" / "public_artifact_manifest.json").read_text()
    )
    listed = set()
    problems = []
    for entry in manifest["entries"]:
        relative = entry["archive_path"].split("/", 1)[1]
        listed.add(relative)
        path = root / relative
        if not path.is_file():
            problems.append(f"missing: {relative}")
        elif (
            path.stat().st_size != entry["public_size_bytes"]
            or sha256_file(path) != entry["public_sha256"]
        ):
            problems.append(f"hash mismatch: {relative}")
    present = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}
    problems += [f"unlisted: {p}" for p in sorted(present - listed - UNLISTED_OK)]
    if problems:
        raise SystemExit(
            f"{len(problems)} package problems:\n  " + "\n  ".join(problems[:20])
        )
    print(
        f"Verified {len(listed)} package entries against public_artifact_manifest.json"
    )
    return len(listed)


def verify_claude28(root: Path) -> bool:
    command = [
        sys.executable,
        str(SCRIPTS / "make_claude28_tables.py"),
        "--evidence-dir",
        str(root),
        "--check",
    ]
    return subprocess.run(command).returncode == 0


def verify_historical(root: Path, keep: Path | None) -> bool:
    work = Path(keep) if keep else Path(tempfile.mkdtemp(prefix="m4bench-verify-"))
    results = work / "results"
    paper = work / "paper"
    results.mkdir(parents=True, exist_ok=True)
    for campaign in sorted((root / "runs").iterdir()):
        for results_root in sorted(p for p in campaign.iterdir() if p.is_dir()):
            link = results / results_root.name
            if not link.exists():
                link.symlink_to(results_root.resolve(), target_is_directory=True)
    if paper.exists():
        shutil.rmtree(paper)
    paper.mkdir()
    for name in ("planning", "tables"):
        shutil.copytree(RELEASE_DIR / name, paper / name)
    env = {
        **os.environ,
        "M4BENCH_RESULTS_DIR": str(results),
        "M4BENCH_PAPER_DIR": str(paper),
        "M4BENCH_FROZEN_REFERENCE": "1",
    }
    ok = True
    for script, tables in HISTORICAL_TABLES.items():
        completed = subprocess.run([sys.executable, str(SCRIPTS / script)], env=env)
        if completed.returncode != 0:
            print(f"FAILED: {script} exited with {completed.returncode}")
            ok = False
            continue
        for table in tables:
            regenerated = paper / "tables" / table
            tracked = RELEASE_DIR / "tables" / table
            if filecmp.cmp(regenerated, tracked, shallow=False):
                print(f"match: {table}")
            elif table in OUTSIDE_PACKAGE:
                print(
                    f"not regenerable from package: {table} ({OUTSIDE_PACKAGE[table]})"
                )
            else:
                print(f"DIFFERS: {table}")
                subprocess.run(["diff", str(tracked), str(regenerated)])
                ok = False
    if not keep:
        shutil.rmtree(work)
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "extracted", type=Path, help="Directory where the package was extracted."
    )
    parser.add_argument(
        "--keep-workdir", type=Path, help="Keep regenerated historical outputs here."
    )
    args = parser.parse_args()
    root = package_root(args.extracted.resolve())
    verify_hashes(root)
    if root.name == "m4bench-evidence-claude-replication":
        ok = verify_claude28(root)
    elif root.name == "m4bench-evidence-submission":
        ok = verify_historical(root, args.keep_workdir)
    else:
        raise SystemExit(f"Unknown package {root.name}")
    if not ok:
        raise SystemExit("Table regeneration from packaged evidence did not match.")
    print("Package verified and tables regenerated.")


if __name__ == "__main__":
    main()
