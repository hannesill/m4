#!/usr/bin/env python3
"""Build an anonymous source-tree archive for review.

The archive is intentionally based on `git ls-files`, not a recursive directory
walk, so `.git/`, ignored credentials, local notes, caches, generated databases,
and operating-system files are excluded by construction.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import tarfile
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

M4_DIR = Path(
    os.environ.get("M4BENCH_M4_DIR", Path(__file__).resolve().parents[4])
).resolve()
DIST_DIR = Path(__file__).resolve().parents[1] / "dist"

TEXT_SUFFIXES = {
    ".cfg",
    ".cff",
    ".csv",
    ".dockerignore",
    ".gitignore",
    ".ini",
    ".json",
    ".jsonl",
    ".lock",
    ".md",
    ".py",
    ".sh",
    ".sql",
    ".tex",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}

ANONYMOUS_REVIEW_EXCLUDES = {
    "CITATION.cff",
}


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_ls_files(include_untracked: bool) -> list[Path]:
    cmd = ["git", "ls-files", "-z", "--cached"]
    if include_untracked:
        cmd.extend(["--others", "--exclude-standard"])
    proc = subprocess.run(
        cmd,
        cwd=M4_DIR,
        check=True,
        capture_output=True,
    )
    return [Path(item.decode()) for item in proc.stdout.split(b"\0") if item]


def configured_redaction_terms() -> list[str]:
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


def redact_text(text: str, *, terms: Iterable[str]) -> tuple[str, bool]:
    redacted = text
    replacements = {
        str(M4_DIR): "<ANON_M4_DIR>",
        str(M4_DIR.parent): "<ANON_WORKSPACE>",
        str(Path.home()): "<ANON_HOME>",
        Path.home().name: "anonymous",
    }
    for old, new in sorted(
        replacements.items(), key=lambda item: len(item[0]), reverse=True
    ):
        if old:
            redacted = redacted.replace(old, new)
    for term in terms:
        redacted = re.sub(re.escape(term), "anonymous", redacted, flags=re.IGNORECASE)
    redacted = re.sub(
        r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        "<ANON_EMAIL>",
        redacted,
        flags=re.IGNORECASE,
    )
    redacted = re.sub(
        r"Copyright \(c\) 2026 .+",
        "Copyright (c) 2026 Anonymous Authors",
        redacted,
    )
    return redacted, redacted != text


def should_treat_as_text(path: Path) -> bool:
    return path.suffix in TEXT_SUFFIXES or path.name in {
        "LICENSE",
        "Dockerfile",
    }


def filtered_paths(paths: Iterable[Path], *, anonymous_review: bool) -> list[Path]:
    out = []
    for path in paths:
        path_text = path.as_posix()
        if not (M4_DIR / path).exists():
            continue
        if anonymous_review and path_text in ANONYMOUS_REVIEW_EXCLUDES:
            continue
        if path_text.startswith(".git/"):
            continue
        out.append(path)
    return sorted(out)


def payload_for(path: Path, terms: list[str]) -> tuple[bytes, bool]:
    raw = (M4_DIR / path).read_bytes()
    if not should_treat_as_text(path):
        return raw, False
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw, False
    redacted, changed = redact_text(text, terms=terms)
    return redacted.encode("utf-8"), changed


def add_json_file(tar: tarfile.TarFile, arcname: Path, data: object) -> None:
    payload = (json.dumps(data, indent=2, sort_keys=True) + "\n").encode("utf-8")
    info = tarfile.TarInfo(str(arcname))
    info.size = len(payload)
    info.mtime = int(datetime.now(UTC).timestamp())
    info.mode = 0o644
    tar.addfile(info, io.BytesIO(payload))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DIST_DIR / "m4bench-source-review.tar.gz",
        help="Output source archive path.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print selected file counts without writing an archive.",
    )
    parser.add_argument(
        "--include-untracked",
        action="store_true",
        help="Also include untracked, non-ignored files. Use only before committing a release snapshot.",
    )
    parser.add_argument(
        "--no-anonymous-review",
        action="store_true",
        help="Keep citation metadata that is omitted by default for double-blind review.",
    )
    args = parser.parse_args()

    anonymous_review = not args.no_anonymous_review
    terms = configured_redaction_terms()
    paths = filtered_paths(
        git_ls_files(include_untracked=args.include_untracked),
        anonymous_review=anonymous_review,
    )

    total_bytes = 0
    redacted_files = []
    manifest = []
    for path in paths:
        payload, redacted = payload_for(path, terms)
        total_bytes += len(payload)
        if redacted:
            redacted_files.append(path.as_posix())
        manifest.append(
            {
                "path": path.as_posix(),
                "size_bytes": len(payload),
                "sha256": sha256_bytes(payload),
                "redacted": redacted,
            }
        )

    print(f"Selected files: {len(paths)}")
    print(f"Redacted text files: {len(redacted_files)}")
    print(f"Uncompressed bytes: {total_bytes}")
    if args.dry_run:
        print("Dry run only; no archive written.")
        return

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(args.output, "w:gz") as tar:
        for path in paths:
            payload, _redacted = payload_for(path, terms)
            info = tarfile.TarInfo(str(Path("m4bench-source-review") / path))
            info.size = len(payload)
            info.mtime = int((M4_DIR / path).stat().st_mtime)
            info.mode = (M4_DIR / path).stat().st_mode & 0o777
            tar.addfile(info, io.BytesIO(payload))
        add_json_file(
            tar,
            Path("m4bench-source-review") / "SOURCE_RELEASE_MANIFEST.json",
            {
                "generated_at": datetime.now(UTC).isoformat(),
                "anonymous_review": anonymous_review,
                "source": "git ls-files",
                "redacted_files": redacted_files,
                "files": manifest,
            },
        )

    digest = sha256_file(args.output)
    Path(str(args.output) + ".sha256").write_text(f"{digest}  {args.output.name}\n")
    print(f"Wrote {args.output}")
    print(f"Wrote {args.output}.sha256")


if __name__ == "__main__":
    main()
