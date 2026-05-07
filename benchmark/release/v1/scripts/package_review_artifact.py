#!/usr/bin/env python3
"""Package paper-facing run artifacts into one review tarball.

The tarball uses the same canonical row selection as the manuscript:
final Codex rows and the May 6 follow-up canonical manifest. Superseded
follow-up retries are included as metadata only, not as run artifact
directories. The Claude sentinel arm can be added explicitly with
``--include-claude``.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from contextlib import contextmanager
from datetime import UTC, datetime
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
PLANNING_DIR = PAPER_DIR / "planning"
DIST_DIR = PAPER_DIR / "dist"

EXPECTED_ARTIFACTS = [
    "result.json",
    "output.csv",
    "instruction.md",
    "trace.jsonl",
    "egress.jsonl",
]
FOLLOWUP_MANIFEST = PLANNING_DIR / "followup_canonical_manifest.json"
FOLLOWUP_SUPERSEDED = PLANNING_DIR / "followup_superseded_runs.json"
RELEASE_MANIFEST = PLANNING_DIR / "artifact_hash_manifest.json"
REDACTED_TEXT_SUFFIXES = {".json", ".jsonl", ".md", ".csv", ".tex"}


sys.path.insert(0, str(BENCHMARK_DIR))

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_final_results import (  # noqa: E402
    CLAUDE_RELEASE,
    CLAUDE_RERUN,
    CODEX_RELEASE,
    CODEX_RERUN,
    OSS_ROOT,
    combine_rows,
    filter_claude_paper_rows,
    load_rows_for_cells,
)


def artifact_paths_for_row(row: dict[str, Any]) -> list[Path]:
    run_dir = Path(row["path"])
    return [run_dir / name for name in EXPECTED_ARTIFACTS if (run_dir / name).exists()]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def configured_redaction_terms() -> list[str]:
    """Return optional author/institution terms supplied outside the release tree."""
    terms = {
        term.strip()
        for term in os.environ.get("M4BENCH_REDACTION_TERMS", "").split(",")
        if term.strip()
    }
    terms_file = os.environ.get("M4BENCH_REDACTION_TERMS_FILE")
    if terms_file:
        path = Path(terms_file).expanduser()
        if path.exists():
            terms.update(
                line.strip()
                for line in path.read_text().splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            )
    return sorted(terms, key=len, reverse=True)


def redact_text(text: str) -> str:
    replacements = {
        str(PAPER_DIR): "<ANON_PAPER_DIR>",
        str(M4_DIR): "<ANON_M4_DIR>",
        str(M4_DIR.parent): "<ANON_WORKSPACE>",
        str(Path.home()): "<ANON_HOME>",
        Path.home().name: "anonymous",
    }
    redacted = text
    for old, new in sorted(
        replacements.items(), key=lambda item: len(item[0]), reverse=True
    ):
        if old:
            redacted = redacted.replace(old, new)
    for term in configured_redaction_terms():
        redacted = re.sub(re.escape(term), "anonymous", redacted, flags=re.IGNORECASE)
    redacted = re.sub(
        r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        "<ANON_EMAIL>",
        redacted,
        flags=re.IGNORECASE,
    )
    redacted = re.sub(r"/Users/[^\s\"']+", "<ANON_LOCAL_PATH>", redacted)
    redacted = re.sub(r"/home/[^\s\"']+", "<ANON_LOCAL_PATH>", redacted)
    redacted = re.sub(r"/var/folders/[^\s\"']+", "<ANON_TMP_PATH>", redacted)
    return redacted


def should_redact(source: Path) -> bool:
    if source.name == "output.csv":
        return False
    return source.suffix in REDACTED_TEXT_SUFFIXES


def packaged_payload(source: Path) -> tuple[bytes, bool]:
    raw = source.read_bytes()
    if not should_redact(source):
        return raw, False
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw, False
    redacted = redact_text(text).encode("utf-8")
    return redacted, redacted != raw


def load_expected_artifacts() -> dict[str, dict[str, Any]]:
    expected: dict[str, dict[str, Any]] = {}
    if RELEASE_MANIFEST.exists():
        for record in json.loads(RELEASE_MANIFEST.read_text()):
            expected[record["relative_path"]] = record

    if FOLLOWUP_MANIFEST.exists():
        manifest = json.loads(FOLLOWUP_MANIFEST.read_text())
        for run in manifest["canonical_runs"]:
            for artifact in run.get("artifacts", []):
                expected[artifact["relative_path"]] = artifact
    return expected


def verify_artifact(source: Path, expected: dict[str, dict[str, Any]]) -> None:
    relative = str(source.relative_to(RESULTS_DIR))
    record = expected.get(relative)
    if record is None:
        raise FileNotFoundError(f"No hash manifest entry for {relative}")
    size = source.stat().st_size
    if size != int(record["size_bytes"]):
        raise ValueError(
            f"Size mismatch for {relative}: expected {record['size_bytes']}, got {size}"
        )
    digest = sha256_file(source)
    if digest != record["sha256"]:
        raise ValueError(f"SHA-256 mismatch for {relative}")


def followup_rows_from_manifest() -> list[dict[str, Any]]:
    manifest = json.loads(FOLLOWUP_MANIFEST.read_text())
    rows = []
    for record in manifest["canonical_runs"]:
        run_dir = RESULTS_DIR / record["relative_run_dir"]
        rows.append({"run_id": record["run_id"], "path": str(run_dir)})
    return rows


def add_file(
    tar: tarfile.TarFile | None,
    source: Path,
    arcname: Path,
    *,
    dry_run: bool,
) -> tuple[int, str, bool]:
    if not source.exists():
        return 0, "", False
    payload, redacted = packaged_payload(source)
    size = len(payload)
    if not dry_run:
        assert tar is not None
        info = tarfile.TarInfo(str(arcname))
        info.size = size
        info.mtime = int(source.stat().st_mtime)
        info.mode = source.stat().st_mode & 0o777
        tar.addfile(info, io.BytesIO(payload))
    return size, sha256_bytes(payload), redacted


def add_text_file(
    tar: tarfile.TarFile | None,
    *,
    arcname: Path,
    text: str,
    dry_run: bool,
) -> tuple[int, int]:
    payload = text.encode("utf-8")
    if not dry_run:
        assert tar is not None
        info = tarfile.TarInfo(str(arcname))
        info.size = len(payload)
        info.mtime = int(datetime.now(UTC).timestamp())
        tar.addfile(info, io.BytesIO(payload))
    return 1, len(payload)


def add_rows(
    tar: tarfile.TarFile | None,
    *,
    rows: list[dict[str, Any]],
    campaign_dir: str,
    expected: dict[str, dict[str, Any]],
    generated_manifest: list[dict[str, Any]] | None = None,
    packaged_manifest: list[dict[str, Any]] | None = None,
    allow_unmanifested: bool = False,
    dry_run: bool,
) -> tuple[int, int]:
    file_count = 0
    byte_count = 0
    assert tar is not None or dry_run
    for row in rows:
        run_dir = Path(row["path"])
        rel_run = run_dir.relative_to(RESULTS_DIR)
        for artifact in artifact_paths_for_row(row):
            relative = str(artifact.relative_to(RESULTS_DIR))
            if relative in expected:
                verify_artifact(artifact, expected)
            elif allow_unmanifested and generated_manifest is not None:
                generated_manifest.append(
                    {
                        "campaign": campaign_dir,
                        "run_id": row.get("run_id", run_dir.name),
                        "artifact": artifact.name,
                        "relative_path": relative,
                        "size_bytes": artifact.stat().st_size,
                        "sha256": sha256_file(artifact),
                    }
                )
            else:
                raise FileNotFoundError(f"No hash manifest entry for {relative}")
            arcname = (
                Path("m4bench-review-artifact")
                / "runs"
                / campaign_dir
                / rel_run
                / artifact.name
            )
            packaged_size, packaged_sha, redacted = add_file(
                tar, artifact, arcname, dry_run=dry_run
            )
            if packaged_manifest is not None:
                packaged_manifest.append(
                    {
                        "archive_path": str(arcname),
                        "source_relative_path": relative,
                        "artifact": artifact.name,
                        "campaign": campaign_dir,
                        "run_id": row.get("run_id", run_dir.name),
                        "size_bytes": packaged_size,
                        "sha256": packaged_sha,
                        "redacted": redacted,
                    }
                )
            byte_count += packaged_size
            file_count += 1
    return file_count, byte_count


def add_json_file(
    tar: tarfile.TarFile | None,
    *,
    arcname: Path,
    data: Any,
    dry_run: bool,
) -> tuple[int, int]:
    return add_text_file(
        tar,
        arcname=arcname,
        text=json.dumps(data, indent=2, sort_keys=True) + "\n",
        dry_run=dry_run,
    )


def add_metadata(
    tar: tarfile.TarFile | None,
    *,
    packaged_manifest: list[dict[str, Any]] | None = None,
    dry_run: bool,
) -> tuple[int, int]:
    metadata_files = [
        PLANNING_DIR / "final_codex_runs.csv",
        PLANNING_DIR / "final_claude_runs.csv",
        PLANNING_DIR / "final_oss_runs.csv",
        PLANNING_DIR / "artifact_hash_manifest.json",
        PLANNING_DIR / "release_metadata_summary.json",
        PLANNING_DIR / "release_metadata_summary.md",
        PLANNING_DIR / "followup_canonical_manifest.json",
        PLANNING_DIR / "followup_canonical_runs.csv",
        PLANNING_DIR / "followup_manifest_summary.md",
        PLANNING_DIR / "followup_results_summary.md",
        PLANNING_DIR / "followup_superseded_runs.json",
        TABLES_DIR / "codex_operational_spec_control.tex",
        TABLES_DIR / "codex_operational_spec_by_task.tex",
        TABLES_DIR / "codex_schema_skill_generalization.tex",
        TABLES_DIR / "codex_followup_integrity.tex",
    ]
    file_count = 0
    byte_count = 0
    assert tar is not None or dry_run
    for source in metadata_files:
        if not source.exists():
            continue
        arcname = (
            Path("m4bench-review-artifact") / "metadata" / source.relative_to(PAPER_DIR)
        )
        packaged_size, packaged_sha, redacted = add_file(
            tar, source, arcname, dry_run=dry_run
        )
        if packaged_manifest is not None:
            packaged_manifest.append(
                {
                    "archive_path": str(arcname),
                    "source_relative_path": str(source.relative_to(PAPER_DIR)),
                    "artifact": source.name,
                    "campaign": "metadata",
                    "size_bytes": packaged_size,
                    "sha256": packaged_sha,
                    "redacted": redacted,
                }
            )
        byte_count += packaged_size
        file_count += 1
    return file_count, byte_count


def human_bytes(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


TABLES_DIR = PAPER_DIR / "tables"


def infer_compression(output: Path, compression: str) -> str:
    if compression != "auto":
        return compression
    name = output.name
    if name.endswith(".tar.gz") or name.endswith(".tgz"):
        return "gzip"
    if name.endswith(".tar.zst") or name.endswith(".tzst"):
        return "zstd"
    return "none"


@contextmanager
def open_archive(output: Path, compression: str):
    if compression == "none":
        with tarfile.open(output, "w") as tar:
            yield tar
        return
    if compression == "gzip":
        with tarfile.open(output, "w:gz") as tar:
            yield tar
        return
    if compression == "zstd":
        zstd = shutil.which("zstd")
        if not zstd:
            raise RuntimeError(
                "zstd is not installed; use --compression gzip or install zstd"
            )
        with output.open("wb") as handle:
            proc = subprocess.Popen(
                [zstd, "-3", "-T0", "-f"], stdin=subprocess.PIPE, stdout=handle
            )
            assert proc.stdin is not None
            try:
                with tarfile.open(fileobj=proc.stdin, mode="w|") as tar:
                    yield tar
            finally:
                proc.stdin.close()
                returncode = proc.wait()
                if returncode != 0:
                    raise RuntimeError(f"zstd failed with exit code {returncode}")
        return
    raise ValueError(f"Unsupported compression: {compression}")


def review_readme(
    *,
    counts: dict[str, tuple[int, int]],
    run_counts: dict[str, int],
    include_claude: bool,
    compression: str,
) -> str:
    lines = [
        "# M4Bench Review Artifact",
        "",
        f"Generated: `{datetime.now(UTC).isoformat()}`",
        f"Compression: `{compression}`",
        "",
        "This archive contains paper-facing per-run artifacts selected by the manuscript scripts.",
        "It is an audit/reproducibility artifact, not a new dataset release.",
        "",
        "## Canonical vs Provenance Runs",
        "",
        "Only run directories under `runs/` are packaged as analysis runs in this archive.",
        "These are the canonical runs selected by the manuscript regeneration scripts.",
        "",
        f"- `runs/codex_primary/`: {run_counts.get('codex_primary', 0)} canonical primary Codex analysis runs. These are the runs used for the paper's primary Codex tables.",
        f"- `runs/codex_followup/`: {run_counts.get('codex_followup', 0)} canonical Codex validity-follow-up analysis runs. These are selected by `metadata/planning/followup_canonical_manifest.json`.",
    ]
    if include_claude:
        lines.append(
            f"- `runs/claude_sentinel/`: {run_counts.get('claude_sentinel', 0)} canonical supplementary Claude sentinel analysis runs."
        )
    if run_counts.get("oss_exploratory"):
        lines.append(
            f"- `runs/oss_exploratory/`: {run_counts['oss_exploratory']} exploratory local OSS runs. These are not publishable paper-facing evidence and should not be pooled with the primary or supplementary analyses."
        )
    lines.extend(
        [
            "",
            "Files under `metadata/` document selection and provenance. They are not, by themselves, analysis-run indexes for this archive.",
            "- `metadata/planning/final_codex_runs.csv` lists the canonical primary Codex rows selected by `make_final_results.py`.",
            "- `metadata/planning/final_claude_runs.csv` lists the canonical supplementary Claude sentinel rows selected by `make_final_results.py`.",
            "- `metadata/planning/final_oss_runs.csv` lists the exploratory local OSS rows reported for context only.",
            "- `metadata/planning/followup_canonical_manifest.json` and `metadata/planning/followup_canonical_runs.csv` list the canonical follow-up rows.",
            "- `metadata/planning/followup_superseded_runs.json` lists retry/replacement follow-up runs retained only for provenance; those directories are not included under `runs/` and should not be counted in the analysis.",
            "- `metadata/planning/artifact_hash_manifest.json` covers the broader retained release/provenance artifact set used to verify files and may include rows or arms not packaged under `runs/`; use the `runs/` directory plus the canonical CSV/manifest files above to identify analysis runs.",
            "- `metadata/planning/oss_exploratory_artifact_manifest.json`, when present, is generated by this packager because exploratory OSS artifacts are outside the paper-facing release manifest.",
        ]
    )
    lines.extend(
        [
            "",
            "## Contents",
            "",
            "- `runs/codex_primary/`: canonical primary Codex run artifacts used in the final analysis",
            "- `runs/codex_followup/`: canonical Codex validity-follow-up run artifacts",
            "- `metadata/`: hash manifests, release metadata, follow-up manifests, and relevant LaTeX tables",
        ]
    )
    if include_claude:
        lines.append(
            "- `runs/claude_sentinel/`: supplementary Claude sentinel run artifacts"
        )
    if run_counts.get("oss_exploratory"):
        lines.append(
            "- `runs/oss_exploratory/`: exploratory local OSS run artifacts, retained for transparency only"
        )
    lines.extend(
        [
            "",
            "Each run directory may include `result.json`, `output.csv`, `instruction.md`, `trace.jsonl`, and `egress.jsonl`.",
            "Source run artifacts were verified against the SHA-256 and byte-size metadata in the included source manifests before packaging.",
            "Text artifacts are redacted during packaging to remove local absolute paths and user-identifying path components for double-blind review.",
            "`metadata/planning/packaged_artifact_manifest.json` records SHA-256 hashes and byte sizes for the packaged, redacted archive entries.",
            "",
            "## Counts",
            "",
        ]
    )
    for label, (files, size) in counts.items():
        lines.append(f"- `{label}`: {files} files, {human_bytes(size)}")
    lines.extend(
        [
            "",
            "## Data Access Boundary",
            "",
            "The archive does not redistribute MIMIC-IV or eICU source databases or generated task databases.",
            "Full task database reconstruction requires independent PhysioNet credentialed access as described in the benchmark repository.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DIST_DIR / "m4bench-paper-results-artifact.tar",
        help="Output archive path.",
    )
    parser.add_argument(
        "--compression",
        choices=["auto", "none", "gzip", "zstd"],
        default="auto",
        help="Archive compression. Auto infers from .tar, .tar.gz/.tgz, or .tar.zst/.tzst.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report selected file counts and byte size without writing a tarball.",
    )
    parser.add_argument(
        "--include-claude",
        action="store_true",
        help="Also include Claude sentinel run artifacts. Codex-only is the default primary paper artifact.",
    )
    parser.add_argument(
        "--include-oss",
        action="store_true",
        help="Also include exploratory local OSS run artifacts under runs/oss_exploratory/.",
    )
    args = parser.parse_args()

    if not FOLLOWUP_MANIFEST.exists():
        raise FileNotFoundError(
            "Run benchmark/release/v1/scripts/make_followup_manifest.py before packaging."
        )

    compression = infer_compression(args.output, args.compression)
    expected = load_expected_artifacts()
    codex_rows, _ = combine_rows(CODEX_RELEASE, CODEX_RERUN)
    claude_rows = []
    if args.include_claude:
        claude_rows_all, _ = combine_rows(CLAUDE_RELEASE, CLAUDE_RERUN)
        claude_rows = filter_claude_paper_rows(claude_rows_all)
    oss_rows = load_rows_for_cells(OSS_ROOT) if args.include_oss else []
    followup_rows = followup_rows_from_manifest()
    oss_manifest: list[dict[str, Any]] = []
    packaged_manifest: list[dict[str, Any]] = []
    run_counts = {
        "codex_primary": len(codex_rows),
        "claude_sentinel": len(claude_rows),
        "codex_followup": len(followup_rows),
        "oss_exploratory": len(oss_rows),
    }

    tar: tarfile.TarFile | None = None
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        if not args.dry_run:
            archive_context = open_archive(args.output, compression)
            tar = archive_context.__enter__()
        counts = {}
        counts["codex_primary"] = add_rows(
            tar,
            rows=codex_rows,
            campaign_dir="codex_primary",
            expected=expected,
            packaged_manifest=packaged_manifest,
            dry_run=args.dry_run,
        )
        if args.include_claude:
            counts["claude_sentinel"] = add_rows(
                tar,
                rows=claude_rows,
                campaign_dir="claude_sentinel",
                expected=expected,
                packaged_manifest=packaged_manifest,
                dry_run=args.dry_run,
            )
        if args.include_oss:
            counts["oss_exploratory"] = add_rows(
                tar,
                rows=oss_rows,
                campaign_dir="oss_exploratory",
                expected=expected,
                generated_manifest=oss_manifest,
                packaged_manifest=packaged_manifest,
                allow_unmanifested=True,
                dry_run=args.dry_run,
            )
        counts["codex_followup"] = add_rows(
            tar,
            rows=followup_rows,
            campaign_dir="codex_followup",
            expected=expected,
            packaged_manifest=packaged_manifest,
            dry_run=args.dry_run,
        )
        counts["metadata"] = add_metadata(
            tar,
            packaged_manifest=packaged_manifest,
            dry_run=args.dry_run,
        )
        if args.include_oss:
            oss_manifest_count = add_json_file(
                tar,
                arcname=Path("m4bench-review-artifact")
                / "metadata"
                / "planning"
                / "oss_exploratory_artifact_manifest.json",
                data={
                    "description": "Generated manifest for exploratory local OSS artifacts packaged outside the paper-facing release manifest.",
                    "source_root": str(OSS_ROOT.relative_to(RESULTS_DIR)),
                    "run_count": len(oss_rows),
                    "artifacts": oss_manifest,
                },
                dry_run=args.dry_run,
            )
            counts["metadata"] = (
                counts["metadata"][0] + oss_manifest_count[0],
                counts["metadata"][1] + oss_manifest_count[1],
            )
        packaged_manifest_count = add_json_file(
            tar,
            arcname=Path("m4bench-review-artifact")
            / "metadata"
            / "planning"
            / "packaged_artifact_manifest.json",
            data={
                "description": "SHA-256 and byte-size manifest for archive entries after double-blind redaction.",
                "redaction": {
                    "enabled": True,
                    "note": "Local absolute paths and configured author/institution redaction terms are replaced in text artifacts.",
                },
                "artifacts": packaged_manifest,
            },
            dry_run=args.dry_run,
        )
        counts["metadata"] = (
            counts["metadata"][0] + packaged_manifest_count[0],
            counts["metadata"][1] + packaged_manifest_count[1],
        )
        counts["readme"] = add_text_file(
            tar,
            arcname=Path("m4bench-review-artifact") / "README.md",
            text=review_readme(
                counts=counts,
                run_counts=run_counts,
                include_claude=args.include_claude,
                compression=compression,
            ),
            dry_run=args.dry_run,
        )
    finally:
        if tar is not None:
            archive_context.__exit__(None, None, None)

    total_files = sum(value[0] for value in counts.values())
    total_bytes = sum(value[1] for value in counts.values())
    print(f"Codex primary runs: {len(codex_rows)}")
    if args.include_claude:
        print(f"Claude sentinel runs: {len(claude_rows)}")
    if args.include_oss:
        print(f"OSS exploratory runs: {len(oss_rows)}")
    print(f"Codex follow-up canonical runs: {len(followup_rows)}")
    for label, (files, size) in counts.items():
        print(f"{label}: {files} files, {human_bytes(size)}")
    print(f"Total: {total_files} files, {human_bytes(total_bytes)}")
    if args.dry_run:
        print("Dry run only; no tarball written.")
    else:
        archive_sha256 = sha256_file(args.output)
        archive_manifest = {
            "description": "Sidecar verification metadata for the M4Bench review artifact archive.",
            "generated_at": datetime.now(UTC).isoformat(),
            "archive": {
                "path": str(args.output),
                "filename": args.output.name,
                "compression": compression,
                "size_bytes": args.output.stat().st_size,
                "sha256": archive_sha256,
            },
            "selection": {
                "include_claude": args.include_claude,
                "include_oss": args.include_oss,
                "run_counts": run_counts,
            },
            "contents": {
                "total_files": total_files,
                "total_uncompressed_bytes": total_bytes,
                "counts": {
                    label: {"files": files, "uncompressed_bytes": size}
                    for label, (files, size) in counts.items()
                },
            },
            "data_access_boundary": (
                "The archive excludes MIMIC-IV, eICU, and generated task databases. "
                "Full reconstruction requires independent PhysioNet credentialed access."
            ),
        }
        Path(str(args.output) + ".sha256").write_text(
            f"{archive_sha256}  {args.output.name}\n"
        )
        Path(str(args.output) + ".manifest.json").write_text(
            json.dumps(archive_manifest, indent=2, sort_keys=True) + "\n"
        )
        print(f"Wrote {args.output}")
        print(f"Wrote {args.output}.sha256")
        print(f"Wrote {args.output}.manifest.json")


if __name__ == "__main__":
    main()
