#!/usr/bin/env python3
"""Build a review artifact bundle from the paper artifact hash manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

EXPECTED_PLANNING_FILES = [
    "final_codex_runs.csv",
    "final_claude_runs.csv",
    "final_oss_runs.csv",
    "release_metadata_summary.json",
    "release_metadata_summary.md",
    "artifact_hash_manifest.json",
]

PAPER_GENERATOR_SCRIPTS = [
    "make_final_results.py",
    "make_release_metadata.py",
]

DEFAULT_OUTPUT_DIR = Path("benchmark/results/m4bench-review-artifacts")


class BundleError(RuntimeError):
    pass


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative_path(raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute() or any(part == ".." for part in path.parts):
        raise BundleError(f"Unsafe manifest relative_path: {raw}")
    if len(path.parts) < 3:
        raise BundleError(f"Manifest relative_path is too short: {raw}")
    return path


def normalize_runner_root(root: str | Path) -> str:
    path = Path(root)
    return path.name


def resolve_repo_path(root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def resolve_archive_path(root: Path, output_dir: Path, path: Path) -> Path:
    if path.is_absolute():
        return path.resolve()
    if len(path.parts) == 1:
        return (output_dir.parent / path).resolve()
    return (root / path).resolve()


def load_manifest(path: Path) -> list[dict]:
    try:
        entries = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise BundleError(f"Could not parse manifest {path}: {exc}") from exc

    if not isinstance(entries, list):
        raise BundleError(f"Manifest must be a JSON list: {path}")

    required = {
        "campaign",
        "run_id",
        "artifact",
        "relative_path",
        "size_bytes",
        "sha256",
    }
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise BundleError(f"Manifest entry {index} is not an object")
        missing = required - set(entry)
        if missing:
            raise BundleError(
                f"Manifest entry {index} is missing keys: {sorted(missing)}"
            )
        safe_relative_path(str(entry["relative_path"]))
        try:
            int(entry["size_bytes"])
        except (TypeError, ValueError) as exc:
            raise BundleError(f"Manifest entry {index} has invalid size_bytes") from exc

    return entries


def filter_entries(entries: list[dict], runner_roots: list[str]) -> list[dict]:
    if not runner_roots:
        return entries

    allowed = {normalize_runner_root(root) for root in runner_roots}
    selected = [
        entry
        for entry in entries
        if safe_relative_path(str(entry["relative_path"])).parts[0] in allowed
    ]
    present = {
        safe_relative_path(str(entry["relative_path"])).parts[0] for entry in selected
    }
    missing = allowed - present
    if missing:
        raise BundleError(
            f"No manifest entries matched runner root(s): {sorted(missing)}"
        )
    return selected


def validate_source_entry(results_root: Path, entry: dict) -> Path:
    relative_path = safe_relative_path(str(entry["relative_path"]))
    source = results_root / relative_path
    if not source.is_file():
        raise BundleError(f"Missing artifact: {source}")

    actual_size = source.stat().st_size
    expected_size = int(entry["size_bytes"])
    if actual_size != expected_size:
        raise BundleError(
            f"Size mismatch for {source}: manifest={expected_size}, actual={actual_size}"
        )

    actual_hash = sha256_file(source)
    if actual_hash != entry["sha256"]:
        raise BundleError(f"SHA-256 mismatch for {source}")

    return source


def copy_artifact(source: Path, destination: Path, file_mode: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if file_mode == "copy":
        shutil.copy2(source, destination)
    elif file_mode == "hardlink":
        try:
            destination.hardlink_to(source)
        except OSError:
            shutil.copy2(source, destination)
    else:
        raise BundleError(f"Unsupported file mode: {file_mode}")


def copy_planning_files(manifest: Path, output_dir: Path, dry_run: bool) -> list[str]:
    planning_dir = manifest.parent
    copied = []
    for name in EXPECTED_PLANNING_FILES:
        source = planning_dir / name
        if not source.exists():
            continue
        copied.append(name)
        if dry_run:
            continue
        destination = output_dir / "planning" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return copied


def copy_provenance(paths: list[Path], output_dir: Path, dry_run: bool) -> list[str]:
    copied = []
    for source in paths:
        source = source.expanduser().resolve()
        if not source.exists():
            raise BundleError(f"Missing provenance path: {source}")
        copied.append(str(source))
        if dry_run:
            continue
        destination = output_dir / "provenance" / source.name
        if source.is_dir():
            shutil.copytree(source, destination, dirs_exist_ok=True)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    return copied


def copy_generator_scripts(
    manifest: Path, output_dir: Path, dry_run: bool
) -> list[str]:
    scripts_dir = manifest.parent.parent / "scripts"
    copied = []
    for name in PAPER_GENERATOR_SCRIPTS:
        source = scripts_dir / name
        if not source.exists():
            continue
        copied.append(str(source))
        if dry_run:
            continue
        destination = output_dir / "paper_scripts" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return copied


def write_readme(output_dir: Path, report: dict) -> None:
    roots = "\n".join(f"- `{root}`: {count} files" for root, count in report["roots"])
    campaigns = "\n".join(
        f"- `{campaign}`: {count} files" for campaign, count in report["campaigns"]
    )
    planning = "\n".join(f"- `{name}`" for name in report["planning_files"])
    scripts = "\n".join(f"- `{Path(path).name}`" for path in report["paper_scripts"])
    if not scripts:
        scripts = "- None"
    provenance = "\n".join(f"- `{path}`" for path in report["provenance_paths"])
    if not provenance:
        provenance = "- None"

    readme = f"""# M4Bench Review Artifacts

Generated at `{report["created_at_utc"]}` by `benchmark/scripts/bundle_review_artifacts.py`.

This bundle is manifest-driven. Files under `benchmark/results/` were copied
from `artifact_hash_manifest.json`, and each source file was verified against
the manifest byte size and SHA-256 hash before bundling.

## Contents

- `benchmark/results/`: retained paper-facing run artifacts
- `planning/`: paper planning and release metadata files
- `paper_scripts/`: copied paper-side scripts that generated final run CSVs and metadata
- `bundle_report.json`: bundle construction summary
- `provenance/`: optional superseded or explanatory artifacts

## Campaigns

{campaigns}

## Result Roots

{roots}

## Planning Files

{planning}

## Paper Scripts

{scripts}

## Provenance

{provenance}

## Verification

To verify the bundled result artifacts after unpacking, compare each file under
`benchmark/results/` against `planning/artifact_hash_manifest.json`.
"""
    (output_dir / "README.md").write_text(readme)


def write_report(output_dir: Path, report: dict) -> None:
    (output_dir / "bundle_report.json").write_text(json.dumps(report, indent=2) + "\n")


def create_tgz(output_dir: Path, archive_path: Path) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(output_dir, arcname=output_dir.name)


def create_tar_zst(output_dir: Path, archive_path: Path, level: int) -> None:
    zstd = shutil.which("zstd")
    if not zstd:
        raise BundleError("zstd is not installed; use --tgz or install zstd")

    archive_path.parent.mkdir(parents=True, exist_ok=True)
    tar_cmd = ["tar", "-cf", "-", "-C", str(output_dir.parent), output_dir.name]
    zstd_cmd = [zstd, f"-{level}", "-T0", "-f", "-o", str(archive_path)]

    tar_proc = subprocess.Popen(tar_cmd, stdout=subprocess.PIPE)
    try:
        zstd_proc = subprocess.run(zstd_cmd, stdin=tar_proc.stdout, check=False)
    finally:
        if tar_proc.stdout:
            tar_proc.stdout.close()
    tar_returncode = tar_proc.wait()

    if tar_returncode != 0:
        raise BundleError(f"tar failed with exit code {tar_returncode}")
    if zstd_proc.returncode != 0:
        raise BundleError(f"zstd failed with exit code {zstd_proc.returncode}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a manifest-verified M4Bench review artifact bundle."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("../m4bench-paper/planning/artifact_hash_manifest.json"),
        help="Path to artifact_hash_manifest.json. Its parent is used as the planning directory.",
    )
    parser.add_argument(
        "--results-root",
        type=Path,
        default=Path("benchmark/results"),
        help="Root containing result campaign directories.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=(
            "Directory to create. Defaults under benchmark/results/ so generated "
            "bundle artifacts stay gitignored."
        ),
    )
    parser.add_argument(
        "--runner-root",
        action="append",
        default=[],
        help=(
            "Optional top-level result root to include, such as "
            "release-20260502-codex-v11. Repeat to create a partial bundle."
        ),
    )
    parser.add_argument(
        "--provenance-path",
        type=Path,
        action="append",
        default=[],
        help="Optional file or directory to copy under provenance/. Repeatable.",
    )
    parser.add_argument(
        "--file-mode",
        choices=["copy", "hardlink"],
        default="copy",
        help="Use hardlink to avoid duplicating large files when staging on the same filesystem.",
    )
    parser.add_argument(
        "--tgz",
        type=Path,
        help=(
            "Optional .tgz archive path to create after staging the bundle. A bare "
            "filename is written next to --output-dir. This uses slow single-threaded "
            "Python gzip."
        ),
    )
    parser.add_argument(
        "--tar-zst",
        type=Path,
        help=(
            "Optional .tar.zst archive path to create using system tar and "
            "multithreaded zstd. A bare filename is written next to --output-dir."
        ),
    )
    parser.add_argument(
        "--zstd-level",
        type=int,
        default=3,
        help="Compression level for --tar-zst. Default: 3.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Remove an existing output directory before creating the bundle.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and summarize without copying files.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = repo_root()
    manifest = resolve_repo_path(root, args.manifest)
    results_root = resolve_repo_path(root, args.results_root)
    output_dir = resolve_repo_path(root, args.output_dir)

    if not manifest.is_file():
        raise BundleError(f"Manifest not found: {manifest}")
    if not results_root.is_dir():
        raise BundleError(f"Results root not found: {results_root}")

    entries = filter_entries(load_manifest(manifest), args.runner_root)
    if not entries:
        raise BundleError("No manifest entries selected")

    if output_dir.exists() and not args.dry_run:
        if not args.force:
            raise BundleError(
                f"Output directory exists; pass --force to replace it: {output_dir}"
            )
        shutil.rmtree(output_dir)

    roots = Counter()
    campaigns = Counter()
    artifacts = Counter()
    total_bytes = 0

    for entry in entries:
        source = validate_source_entry(results_root, entry)
        relative_path = safe_relative_path(str(entry["relative_path"]))
        roots[relative_path.parts[0]] += 1
        campaigns[str(entry["campaign"])] += 1
        artifacts[str(entry["artifact"])] += 1
        total_bytes += int(entry["size_bytes"])

        if not args.dry_run:
            destination = output_dir / "benchmark" / "results" / relative_path
            copy_artifact(source, destination, args.file_mode)

    planning_files = copy_planning_files(manifest, output_dir, args.dry_run)
    paper_scripts = copy_generator_scripts(manifest, output_dir, args.dry_run)
    provenance_paths = copy_provenance(args.provenance_path, output_dir, args.dry_run)

    report = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "manifest": str(manifest),
        "results_root": str(results_root),
        "output_dir": str(output_dir),
        "file_mode": args.file_mode,
        "dry_run": bool(args.dry_run),
        "selected_entries": len(entries),
        "selected_bytes": total_bytes,
        "campaigns": sorted(campaigns.items()),
        "roots": sorted(roots.items()),
        "artifacts": sorted(artifacts.items()),
        "planning_files": planning_files,
        "paper_scripts": paper_scripts,
        "provenance_paths": provenance_paths,
    }
    archive_jobs = []
    if args.tgz:
        tgz_path = resolve_archive_path(root, output_dir, args.tgz)
        archive_jobs.append(("tgz", tgz_path))
    if args.tar_zst:
        tar_zst_path = resolve_archive_path(root, output_dir, args.tar_zst)
        archive_jobs.append(("tar.zst", tar_zst_path))
    if archive_jobs:
        report["archives"] = [
            {"format": archive_format, "path": str(path)}
            for archive_format, path in archive_jobs
        ]
        if len(archive_jobs) == 1:
            report["archive"] = str(archive_jobs[0][1])

    if args.dry_run:
        print(json.dumps(report, indent=2))
        return 0

    write_report(output_dir, report)
    write_readme(output_dir, report)

    for archive_format, archive_path in archive_jobs:
        if archive_format == "tgz":
            create_tgz(output_dir, archive_path)
        elif archive_format == "tar.zst":
            create_tar_zst(output_dir, archive_path, args.zstd_level)

    print(f"Created bundle: {output_dir}")
    print(f"Artifacts: {len(entries)} files, {total_bytes:,} bytes")
    for archive in report.get("archives", []):
        print(f"Archive ({archive['format']}): {archive['path']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BundleError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
