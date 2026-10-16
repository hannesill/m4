#!/usr/bin/env python3
"""Derive valid copies of malformed historical result.json files.

The May 2026 review archive redacted local paths with a regex that consumed
JSON escape backslashes (for example `/var/folders/...\\"`), which truncated
strings inside `agent_result` diagnostic text. The evaluator fields and all
other top-level metadata are intact.

This script never edits original bytes. It streams an archive (or walks a
directory), and for every `result.json` that fails to parse it writes a
derived copy in which the `agent_result` object is rebuilt from:

* scalar fields that are still recoverable line by line (returncode,
  elapsed_seconds, status, ...), and
* `unparsed_original_text`, the verbatim malformed block as a JSON string.

All other top-level fields are copied from the original text unchanged. A
lineage file maps every original path and SHA-256 to the derived SHA-256.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from archive_io import iter_members, sha256_bytes

REPAIR_METHOD = "rebuild-agent-result-v1"
REPAIR_DESCRIPTION = (
    "Original agent_result block replaced by recovered scalar fields plus "
    "`unparsed_original_text` (the verbatim malformed block as a JSON string); "
    "every other top-level field is copied unchanged from the original bytes."
)
TOP_LEVEL_KEY = re.compile(r'^  "([^"]+)": ', re.MULTILINE)
SCALAR_LINE = re.compile(
    r'^    "(?P<key>[A-Za-z_][A-Za-z0-9_]*)": '
    r'(?P<value>-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?|true|false|null|"[^"\\]*"),?$'
)


class RepairError(ValueError):
    pass


def top_level_spans(text: str) -> list[tuple[str, int, int]]:
    """Return (key, start, end) character spans for each top-level member."""
    starts = [(match.group(1), match.start()) for match in TOP_LEVEL_KEY.finditer(text)]
    closing = text.rstrip().rfind("\n}")
    if not starts or closing < 0:
        raise RepairError("not an indented JSON object")
    spans = []
    for index, (key, start) in enumerate(starts):
        end = starts[index + 1][1] if index + 1 < len(starts) else closing + 1
        spans.append((key, start, end))
    return spans


def member_value_text(text: str, key: str, start: int, end: int) -> str:
    body = text[start:end].rstrip()
    body = body.removesuffix(",")
    prefix = f'  "{key}": '
    if not body.startswith(prefix):
        raise RepairError(f"unexpected layout for {key}")
    return body[len(prefix) :]


def recovered_agent_fields(block: str) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for line in block.splitlines():
        match = SCALAR_LINE.match(line)
        if match and match.group("key") not in fields:
            fields[match.group("key")] = json.loads(match.group("value"))
    return fields


def repair_text(text: str) -> tuple[dict[str, Any], list[str]]:
    """Return a repaired JSON object and the recovered agent_result fields."""
    members: dict[str, Any] = {}
    recovered: list[str] = []
    for key, start, end in top_level_spans(text):
        raw_value = member_value_text(text, key, start, end)
        if key == "agent_result":
            fields = recovered_agent_fields(raw_value)
            recovered = sorted(fields)
            members[key] = {**fields, "unparsed_original_text": raw_value}
            continue
        try:
            members[key] = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise RepairError(f"field {key} is also malformed: {exc}") from exc
    if "agent_result" not in members:
        raise RepairError("malformed JSON without an agent_result block")
    members["derived_repair"] = {
        "method": REPAIR_METHOD,
        "description": REPAIR_DESCRIPTION,
        "recovered_agent_result_fields": recovered,
    }
    return members, recovered


def derived_payload(members: dict[str, Any]) -> bytes:
    return (json.dumps(members, indent=2) + "\n").encode("utf-8")


def iter_result_files(source: Path):
    if source.is_dir():
        for path in sorted(source.rglob("result.json")):
            yield str(path.relative_to(source)), path.read_bytes()
        return
    for member, payload in iter_members(
        source, lambda name: name.endswith("/result.json")
    ):
        yield member.name, payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source", type=Path, help="Archive (.tar/.tar.zst) or directory to scan."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory for derived copies, laid out by original member path.",
    )
    parser.add_argument(
        "--lineage",
        type=Path,
        required=True,
        help="Where to write the original-to-derived lineage JSON.",
    )
    args = parser.parse_args()

    records = []
    failures = []
    scanned = 0
    for name, payload in iter_result_files(args.source):
        scanned += 1
        try:
            json.loads(payload)
            continue
        except json.JSONDecodeError as exc:
            parse_error = str(exc)
        try:
            members, recovered = repair_text(payload.decode("utf-8"))
        except (RepairError, UnicodeDecodeError) as exc:
            failures.append({"original_path": name, "error": str(exc)})
            continue
        derived = derived_payload(members)
        json.loads(derived)
        destination = args.output_dir / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(derived)
        records.append(
            {
                "original_path": name,
                "run_id": members.get("run_id"),
                "original_sha256": sha256_bytes(payload),
                "original_size_bytes": len(payload),
                "original_parse_error": parse_error,
                "derived_path": name,
                "derived_sha256": sha256_bytes(derived),
                "derived_size_bytes": len(derived),
                "repair_method": REPAIR_METHOD,
                "recovered_agent_result_fields": recovered,
            }
        )

    lineage = {
        "description": (
            "Derived valid-JSON copies of malformed result.json files. Original "
            "bytes are unchanged in the source archive; derived copies are keyed "
            "by original member path."
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": args.source.name,
        "repair_method": REPAIR_METHOD,
        "repair_description": REPAIR_DESCRIPTION,
        "scanned_result_files": scanned,
        "repaired": len(records),
        "unrepairable": failures,
        "records": records,
    }
    args.lineage.parent.mkdir(parents=True, exist_ok=True)
    args.lineage.write_text(json.dumps(lineage, indent=2) + "\n")
    print(f"Scanned {scanned} result.json files; repaired {len(records)}.")
    if failures:
        print(f"{len(failures)} files could not be repaired; see {args.lineage}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
