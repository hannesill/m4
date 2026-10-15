#!/usr/bin/env python3
"""Build the open (non-credentialed) M4Bench evidence packages.

Two packages share one format:

* ``claude28``: the canonical 560-run July 2026 Claude campaign, read from the
  local results roots plus the collaborator archive.
* ``historical``: the 1,400 run directories of the original May 2026 review
  archive (primary Codex, Claude sentinel, Codex follow-up, exploratory OSS),
  with malformed ``result.json`` files replaced by documented derived copies.

Every source file is hashed and compared with its declared manifest before it
is transformed; any missing, extra, or mismatched file aborts the build and
removes the partial archive. The open package never contains row-level agent
outputs: ``output.csv`` becomes ``output_summary.json`` (columns, row count,
source hash). Traces and diagnostic text are sanitized structurally
(tool/command output replaced by placeholders, shifted datetimes and MIMIC
identifiers removed). ``metadata/public_artifact_manifest.json`` maps every
source hash to its public hash.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from archive_io import open_tar_stream, sha256_bytes, sha256_file
from sanitize_artifacts import (
    SanitizationReport,
    SanitizerConfig,
    load_private_patterns,
    sanitized_payload_for,
)

M4_DIR = Path(
    os.environ.get("M4BENCH_M4_DIR", Path(__file__).resolve().parents[4])
).resolve()
RELEASE_DIR = Path(__file__).resolve().parents[1]
RESULTS_DIR = Path(
    os.environ.get("M4BENCH_RESULTS_DIR", M4_DIR / "benchmark" / "results")
).resolve()
REQUIRED = [
    "result.json",
    "output.csv",
    "trace.jsonl",
    "instruction.md",
    "egress.jsonl",
]
FIXED_MTIME = 1790726400  # 2026-10-01T00:00:00Z; keeps entry metadata stable.
CHUNK = 4 * 1024 * 1024
ORIGINAL_ARCHIVE_PREFIX = "m4bench-review-artifact/"
DATA_BOUNDARY = (
    "This open package contains no MIMIC-IV or eICU source data, task databases, "
    "reference outputs, or row-level agent outputs. Full reconstruction requires "
    "independent PhysioNet credentialed access."
)


class EvidenceError(SystemExit):
    pass


@dataclass(frozen=True)
class Expected:
    source_path: str  # path in the source archive or results tree
    archive_path: str  # path inside the public package
    sha256: str
    size_bytes: int


# --------------------------------------------------------------------------
# Expected file sets


def claude28_expected() -> tuple[dict[str, Expected], dict[str, Expected]]:
    """Return (local, collaborator-archive) expectations keyed by source path."""
    manifest = json.loads(
        (
            RELEASE_DIR / "planning" / "claude28" / "claude28_canonical_manifest.json"
        ).read_text()
    )
    local: dict[str, Expected] = {}
    remote: dict[str, Expected] = {}
    for run in manifest["runs"]:
        for name, artifact in run["artifacts"].items():
            source = f"{run['source_run_path']}/{name}"
            expected = Expected(
                source_path=source,
                archive_path=f"runs/claude_native_28/{run['run_id']}/{name}",
                sha256=artifact["sha256"],
                size_bytes=artifact["size_bytes"],
            )
            if run["source"] == "Collaborator canonical archive":
                remote[source] = expected
            else:
                local[source] = expected
    return local, remote


def historical_expected(manifest_path: Path) -> dict[str, Expected]:
    manifest = json.loads(manifest_path.read_text())
    expected = {}
    for record in manifest["artifacts"]:
        path = record["archive_path"]
        if record["campaign"] == "metadata":
            continue
        expected[path] = Expected(
            source_path=path,
            archive_path=path.removeprefix(ORIGINAL_ARCHIVE_PREFIX),
            sha256=record["sha256"],
            size_bytes=int(record["size_bytes"]),
        )
    return expected


# --------------------------------------------------------------------------
# Transformations


def copy_verified(handle: IO[bytes], destination: Path, expected: Expected) -> None:
    digest = hashlib.sha256()
    size = 0
    with destination.open("wb") as out:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
            size += len(chunk)
            out.write(chunk)
    check_hash(expected, digest.hexdigest(), size)


def check_hash(expected: Expected, sha256: str, size: int) -> None:
    if size != expected.size_bytes or sha256 != expected.sha256:
        raise EvidenceError(
            f"Source mismatch for {expected.source_path}: expected "
            f"{expected.sha256}/{expected.size_bytes}, got {sha256}/{size}"
        )


def csv_summary(handle: IO[bytes], expected: Expected) -> bytes:
    """Hash and count an output CSV without retaining any row."""
    digest = hashlib.sha256()
    size = 0
    newlines = 0
    first = b""
    last = b""
    for chunk in iter(lambda: handle.read(CHUNK), b""):
        digest.update(chunk)
        size += len(chunk)
        newlines += chunk.count(b"\n")
        if len(first) < 65536:
            first += chunk[: 65536 - len(first)]
        last = chunk[-1:]
    check_hash(expected, digest.hexdigest(), size)
    header_line = first.split(b"\n", 1)[0].decode("utf-8", "replace")
    columns = next(csv.reader([header_line]), []) if header_line else []
    lines = newlines + (1 if size and last != b"\n" else 0)
    summary = {
        "source_file": "output.csv",
        "source_sha256": expected.sha256,
        "source_size_bytes": expected.size_bytes,
        "columns": columns,
        "data_rows": max(lines - 1, 0),
        "note": (
            "Row-level agent outputs are derived from credentialed PhysioNet data "
            "and are withheld from the open package. Evaluator results for this "
            "file are in result.json; source_sha256 identifies the retained file."
        ),
    }
    return (json.dumps(summary, indent=2) + "\n").encode("utf-8")


def count_malformed_json_lines(payload: bytes) -> int:
    count = 0
    for line in payload.decode("utf-8", "replace").split("\n"):
        if line.lstrip().startswith("{"):
            try:
                json.loads(line)
            except json.JSONDecodeError:
                count += 1
    return count


def sanitize_file(
    path: Path,
    name: str,
    *,
    config: SanitizerConfig,
    report: SanitizationReport,
    rel_path: str,
) -> bytes:
    payload, file_report = sanitized_payload_for(
        path, rel_path=Path(rel_path), config=config
    )
    report.files.append(file_report)
    if file_report.action == "skipped":
        raise EvidenceError(f"Sanitizer skipped required file {rel_path}")
    if name == "result.json":
        try:
            json.loads(payload)
        except json.JSONDecodeError as exc:
            raise EvidenceError(
                f"Sanitized {rel_path} is not valid JSON: {exc}"
            ) from exc
    # An event that does not parse cannot have its tool output replaced, so the
    # sanitizer withholds it; none may reach the package.
    if name.endswith(".jsonl") and count_malformed_json_lines(payload):
        raise EvidenceError(f"Sanitized {rel_path} still has malformed JSON events")
    return payload


# --------------------------------------------------------------------------
# Package writer


class PackageWriter:
    def __init__(self, output: Path | None, top: str):
        self.output = output
        self.top = top
        self.records: list[dict[str, Any]] = []
        self._proc: subprocess.Popen | None = None
        self._tar: tarfile.TarFile | None = None
        self._handle: IO[bytes] | None = None
        if output is None:
            return
        zstd = shutil.which("zstd")
        if not zstd:
            raise RuntimeError("zstd is required")
        output.parent.mkdir(parents=True, exist_ok=True)
        self._handle = output.open("wb")
        self._proc = subprocess.Popen(
            [zstd, "-10", "-T0", "--long=27", "-q", "-f"],
            stdin=subprocess.PIPE,
            stdout=self._handle,
        )
        assert self._proc.stdin is not None
        self._tar = tarfile.open(
            fileobj=self._proc.stdin, mode="w|", format=tarfile.PAX_FORMAT
        )

    def add(
        self, archive_path: str, payload: bytes, record: dict[str, Any] | None = None
    ) -> None:
        if record is not None:
            self.records.append(
                {
                    "archive_path": f"{self.top}/{archive_path}",
                    **record,
                    "public_sha256": sha256_bytes(payload),
                    "public_size_bytes": len(payload),
                }
            )
        if self._tar is None:
            return
        info = tarfile.TarInfo(f"{self.top}/{archive_path}")
        info.size = len(payload)
        info.mtime = FIXED_MTIME
        info.mode = 0o644
        self._tar.addfile(info, io.BytesIO(payload))

    def close(self) -> None:
        if self._tar is None:
            return
        self._tar.close()
        assert self._proc is not None and self._proc.stdin is not None
        self._proc.stdin.close()
        code = self._proc.wait()
        assert self._handle is not None
        self._handle.close()
        if code != 0:
            raise RuntimeError(f"zstd failed with exit code {code}")

    def abort(self) -> None:
        try:
            if self._tar is not None:
                self._tar.close()
            if self._proc is not None:
                if self._proc.stdin:
                    self._proc.stdin.close()
                self._proc.wait()
            if self._handle is not None:
                self._handle.close()
        finally:
            if self.output is not None and self.output.exists():
                self.output.unlink()


def process_source(
    writer: PackageWriter,
    handle: IO[bytes],
    expected: Expected,
    *,
    config: SanitizerConfig,
    report: SanitizationReport,
    scratch: Path,
    repaired: dict[str, dict[str, Any]],
    repairs_dir: Path | None,
) -> None:
    name = Path(expected.archive_path).name
    base = {
        "source_path": expected.source_path,
        "source_sha256": expected.sha256,
        "source_size_bytes": expected.size_bytes,
    }
    if name == "output.csv":
        payload = csv_summary(handle, expected)
        target = str(Path(expected.archive_path).with_name("output_summary.json"))
        writer.add(target, payload, {**base, "transform": "csv-summary"})
        return

    temp = scratch / name
    copy_verified(handle, temp, expected)
    transform = "sanitized-json" if name == "result.json" else "sanitized-text"
    source_for_sanitizer = temp
    repair = repaired.get(expected.source_path)
    if repair is not None:
        assert repairs_dir is not None
        # The member was just verified against `expected`; the repair must have
        # been made from those bytes, not from another file at the same path.
        if (repair["original_sha256"], repair["original_size_bytes"]) != (
            expected.sha256,
            expected.size_bytes,
        ):
            raise EvidenceError(
                f"Repair lineage names another original for {expected.source_path}"
            )
        derived = repairs_dir / expected.source_path
        if sha256_file(derived) != repair["derived_sha256"]:
            raise EvidenceError(f"Derived repair copy changed: {derived}")
        source_for_sanitizer = derived
        transform = "repaired-then-sanitized-json"
        base = {
            **base,
            "derived_sha256": repair["derived_sha256"],
            "repair_method": repair["repair_method"],
        }
    payload = sanitize_file(
        source_for_sanitizer,
        name,
        config=config,
        report=report,
        rel_path=expected.archive_path,
    )
    temp.unlink()
    writer.add(expected.archive_path, payload, {**base, "transform": transform})


def iter_local(expected: dict[str, Expected]) -> Iterator[tuple[Expected, IO[bytes]]]:
    for source, item in sorted(expected.items()):
        path = M4_DIR / source
        if not path.is_file():
            path = RESULTS_DIR / Path(source).relative_to("benchmark/results")
        if not path.is_file():
            raise EvidenceError(f"Missing local source file: {source}")
        with path.open("rb") as handle:
            yield item, handle


def iter_archive(
    archive: Path, expected: dict[str, Expected]
) -> Iterator[tuple[Expected, IO[bytes]]]:
    with open_tar_stream(archive) as tar:
        for member in tar:
            if member.isfile() and member.name in expected:
                handle = tar.extractfile(member)
                assert handle is not None
                yield expected[member.name], handle


def add_metadata_files(writer: PackageWriter, files: dict[str, Path]) -> None:
    for archive_path, source in sorted(files.items()):
        if not source.is_file():
            raise EvidenceError(f"Missing metadata file: {source}")
        payload = source.read_bytes()
        writer.add(
            archive_path,
            payload,
            {
                # Relative to this checkout, also when M4BENCH_M4_DIR points at
                # another one that holds the private results.
                "source_path": str(source.relative_to(RELEASE_DIR.parents[2])),
                "source_sha256": sha256_bytes(payload),
                "source_size_bytes": len(payload),
                "transform": "verbatim-release-metadata",
            },
        )


def readme(kind: str, counts: dict[str, int], generated_at: str) -> str:
    title = {
        "claude28": "M4Bench July 2026 Claude replication: per-run evidence (open package)",
        "historical": "M4Bench May 2026 submission campaigns: per-run evidence (open package)",
    }[kind]
    lines = [
        f"# {title}",
        "",
        f"Generated: `{generated_at}` by `benchmark/release/v1/scripts/package_public_evidence.py`.",
        "",
        DATA_BOUNDARY,
        "",
        "## Layout",
        "",
        "- `runs/<campaign>/.../result.json`: run identity, isolation checks, evaluator results.",
        "  The agent's stdout tail is sanitized like a trace.",
        "- `runs/<campaign>/.../trace.jsonl`: agent trace; tool and command outputs are replaced by",
        "  `<REDACTED_TOOL_OUTPUT chars=... hmac_prefix=...>` placeholders; agent messages, code, and SQL are kept.",
        "- `runs/<campaign>/.../output_summary.json`: column names, row count, and SHA-256 of the withheld",
        "  `output.csv`. Runs that wrote no output have no summary.",
        "- `runs/<campaign>/.../instruction.md`, `egress.jsonl`: task instruction and network egress log.",
        "  The exploratory OSS runs have no egress log.",
        "- `metadata/public_artifact_manifest.json`: for every entry, the source path, source SHA-256,",
        "  transform, and public SHA-256.",
        "- `metadata/SANITIZATION_REPORT.json`: per-file sanitization actions (no pattern text or salt).",
        "",
        "## What is withheld",
        "",
        "- Tool and command outputs, because they contain query results from credentialed data.",
        "- Events that are not valid JSON in the source (`redacted_unparseable_event`), and truncated",
        "  events at the start of a stdout tail (`<REDACTED_EVENT_FRAGMENT ...>`): their tool output",
        "  cannot be separated from agent text, so the whole event is withheld.",
        "- In agent text that is kept: credentials, MIMIC and eICU identifiers (pseudonymized),",
        "  date-shifted timestamps, patient ages, and rows that start with an identifier.",
        "- Placeholder digests are keyed with a private salt and cannot be matched to source values.",
        "",
        "Agent messages are otherwise kept as written and can describe what the agent saw.",
        "",
        "## License",
        "",
        "MIT, as for the M4 repository. The package holds no PhysioNet source data.",
        "",
        "## Counts",
        "",
    ]
    lines += [f"- {label}: {value}" for label, value in sorted(counts.items())]
    if kind == "historical":
        lines += [
            "",
            "## Repaired result.json files",
            "",
            "322 `result.json` files in the original review archive were malformed because",
            "packaging-time path redaction consumed JSON escape characters inside",
            "`agent_result` diagnostic text. Their evaluator fields were never affected.",
            "Those entries are built from derived copies (`transform: repaired-then-sanitized-json`);",
            "`metadata/historical_result_json_repair_lineage.json` maps each original hash",
            "to the derived and public hashes. Original bytes are unchanged in the private archive.",
            "",
            "The same redaction left some trace events that do not parse; they are the",
            "`redacted_unparseable_event` entries counted above.",
            "",
            "This package supersedes the review archive.",
        ]
    lines += [
        "",
        "## Verification",
        "",
        "From a checkout of the tagged M4 release, after extracting this archive:",
        "",
        "```bash",
        "python benchmark/release/v1/scripts/verify_public_evidence.py <extracted-dir>",
        "```",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=["claude28", "historical"])
    parser.add_argument(
        "--output", type=Path, help="Output .tar.zst (omit with --verify-only)."
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Verify and transform without writing.",
    )
    parser.add_argument(
        "--collaborator-archive", type=Path, help="claude28: collaborator run archive."
    )
    parser.add_argument(
        "--source-archive", type=Path, help="historical: original review archive."
    )
    parser.add_argument(
        "--expected-manifest",
        type=Path,
        help="historical: packaged_artifact_manifest.json extracted from the source archive.",
    )
    parser.add_argument(
        "--repairs-dir", type=Path, help="historical: derived result.json copies."
    )
    parser.add_argument(
        "--repair-lineage", type=Path, help="historical: repair_result_json.py lineage."
    )
    parser.add_argument(
        "--salt-file", type=Path, required=True, help="Private HMAC salt file."
    )
    parser.add_argument(
        "--private-patterns", type=Path, help="Private literal/regex redaction terms."
    )
    parser.add_argument(
        "--scratch-dir", type=Path, help="Directory for per-file temporary copies."
    )
    args = parser.parse_args()
    if not args.verify_only and args.output is None:
        parser.error("--output is required unless --verify-only is given")

    salt = args.salt_file.read_bytes().strip()
    if not salt:
        raise EvidenceError("Empty salt file")
    config = SanitizerConfig(
        salt=salt,
        private_patterns=load_private_patterns(args.private_patterns),
        collect_input_hashes=False,
    )
    report = SanitizationReport(source="<private>", output="<public>")
    report.private_patterns_loaded = bool(
        config.private_patterns.literals or config.private_patterns.regexes
    )
    report.private_literal_patterns = len(config.private_patterns.literals)
    report.private_regex_patterns = len(config.private_patterns.regexes)
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    repaired: dict[str, dict[str, Any]] = {}
    metadata: dict[str, Path] = {}
    if args.kind == "claude28":
        if not args.collaborator_archive:
            parser.error("claude28 requires --collaborator-archive")
        local, remote = claude28_expected()
        expected_total = {**local, **remote}
        sources = [
            ("local", lambda: iter_local(local)),
            ("archive", lambda: iter_archive(args.collaborator_archive, remote)),
        ]
        top = "m4bench-evidence-claude-replication"
        planning = RELEASE_DIR / "planning" / "claude28"
        metadata = {
            f"metadata/claude28/{path.relative_to(planning)}": path
            for path in sorted(planning.rglob("*"))
            if path.is_file()
        }
        for table in sorted((RELEASE_DIR / "tables").glob("claude28_*.tex")):
            metadata[f"metadata/tables/{table.name}"] = table
        metadata["metadata/tables/task_details.tex"] = (
            RELEASE_DIR / "tables" / "task_details.tex"
        )
    else:
        for option in (
            "source_archive",
            "expected_manifest",
            "repairs_dir",
            "repair_lineage",
        ):
            if getattr(args, option) is None:
                parser.error(f"historical requires --{option.replace('_', '-')}")
        expected_total = historical_expected(args.expected_manifest)
        lineage = json.loads(args.repair_lineage.read_text())
        repaired = {record["original_path"]: record for record in lineage["records"]}
        sources = [
            ("archive", lambda: iter_archive(args.source_archive, expected_total))
        ]
        top = "m4bench-evidence-submission"
        planning = RELEASE_DIR / "planning"
        metadata = {
            f"metadata/planning/{path.name}": path
            for path in sorted(planning.glob("*"))
            if path.is_file() and path.suffix in {".csv", ".json", ".md"}
        }

    writer = PackageWriter(None if args.verify_only else args.output, top)
    seen: set[str] = set()
    campaigns: Counter[str] = Counter()
    try:
        with tempfile.TemporaryDirectory(
            prefix="m4bench-evidence-", dir=args.scratch_dir
        ) as tmp:
            scratch = Path(tmp)
            for label, factory in sources:
                for expected, handle in factory():
                    if expected.source_path in seen:
                        raise EvidenceError(
                            f"Duplicate source entry {expected.source_path}"
                        )
                    process_source(
                        writer,
                        handle,
                        expected,
                        config=config,
                        report=report,
                        scratch=scratch,
                        repaired=repaired,
                        repairs_dir=args.repairs_dir,
                    )
                    seen.add(expected.source_path)
                    campaigns[expected.archive_path.split("/")[1]] += 1
                    if len(seen) % 500 == 0:
                        print(
                            f"{label}: {len(seen)}/{len(expected_total)} files verified",
                            flush=True,
                        )
        missing = sorted(set(expected_total) - seen)
        if missing:
            raise EvidenceError(
                f"{len(missing)} expected source files were not found, e.g. {missing[:5]}"
            )
        unused_repairs = sorted(set(repaired) - seen)
        if unused_repairs:
            raise EvidenceError(
                f"Repair lineage entries without source files: {unused_repairs[:5]}"
            )

        add_metadata_files(writer, metadata)
        if repaired:
            public_hash = {r["source_path"]: r["public_sha256"] for r in writer.records}
            public_lineage = {
                "description": (
                    "Original-to-derived-to-public hash lineage for malformed historical "
                    "result.json files. Original bytes remain in the private review archive."
                ),
                "source_archive": args.source_archive.name,
                "source_archive_sha256": sha256_file(args.source_archive)
                if not args.verify_only
                else None,
                "repair_method": lineage["repair_method"],
                "repair_description": lineage["repair_description"],
                "records": [
                    {**record, "public_sha256": public_hash[record["original_path"]]}
                    for record in lineage["records"]
                ],
            }
            writer.add(
                "metadata/historical_result_json_repair_lineage.json",
                (json.dumps(public_lineage, indent=2) + "\n").encode("utf-8"),
            )
        counts = {
            f"files from campaign {name}": value for name, value in campaigns.items()
        }
        counts["run directories"] = len({str(Path(p).parent) for p in seen})
        counts["verified source files"] = len(seen)
        counts["repaired result.json"] = len(repaired)
        counts["withheld unparseable events or fragments"] = sum(
            item.withheld_unparseable for item in report.files
        )
        writer.add(
            "metadata/SANITIZATION_REPORT.json",
            (json.dumps(report.to_json(), indent=2, sort_keys=True) + "\n").encode(
                "utf-8"
            ),
        )
        writer.add(
            "metadata/public_artifact_manifest.json",
            (
                json.dumps(
                    {
                        "description": "Source-to-public hash lineage for every packaged entry.",
                        "generated_at": generated_at,
                        "entries": writer.records,
                    },
                    indent=2,
                )
                + "\n"
            ).encode("utf-8"),
        )
        writer.add("README.md", readme(args.kind, counts, generated_at).encode("utf-8"))
        writer.close()
    except BaseException:
        writer.abort()
        raise

    print(json.dumps(counts, indent=2))
    if args.verify_only:
        print("Verification only; no archive written.")
        return
    digest = sha256_file(args.output)
    Path(f"{args.output}.sha256").write_text(f"{digest}  {args.output.name}\n")
    Path(f"{args.output}.manifest.json").write_text(
        json.dumps(
            {
                "archive": {
                    "filename": args.output.name,
                    "size_bytes": args.output.stat().st_size,
                    "sha256": digest,
                    "compression": "zstd",
                },
                "package": top,
                "generated_at": generated_at,
                "counts": counts,
                "data_access_boundary": DATA_BOUNDARY,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"Wrote {args.output} ({args.output.stat().st_size} bytes, sha256 {digest})")


if __name__ == "__main__":
    main()
