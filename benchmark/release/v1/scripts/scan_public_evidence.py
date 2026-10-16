#!/usr/bin/env python3
"""Scan an extracted open evidence package for residual private content.

This scanner is deliberately independent of `sanitize_artifacts.py`: it defines
its own patterns and checks the structure of the package, so a blind spot in
the sanitizer is not inherited here. It reports counts per check and file name
and exits non-zero on any hit.

Structural checks:

* every JSON event line in a trace parses, and every tool or command output in
  it is a `<REDACTED_TOOL_OUTPUT ...>` placeholder;
* `result.json` agent stdout holds only valid events or placeholders, and no
  verbatim unparsed agent block;
* no row-level file kinds (`output.csv`, databases) are present.

Content checks run on every string at every JSON nesting depth, with escaped
newlines and quotes expanded first so that values inside JSON-in-JSON text are
visible: credentials, raw MIMIC identifiers, shifted datetimes, rows that start
with an identifier, stated patient ages, home paths, e-mail addresses, and
configured private terms and patterns. In eICU runs, whose stay identifiers
are plain 6-7 digit integers, any such integer that is not written as a count
is flagged. JSON numbers are checked under identifier keys and their plurals,
and in tool input, where the agent chooses the keys, wherever they have an
identifier's shape and their key does not name a duration or a limit. Other
numbers of that shape are byte counts, token counters and seeds. Git patch
headers are exempt from the e-mail check because they reproduce public commit
metadata.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterator
from pathlib import Path
from typing import Any

ID_KEYS = {
    "subject_id",
    "hadm_id",
    "stay_id",
    "patientunitstayid",
    "patienthealthsystemstayid",
    "uniquepid",
}
TOOL_OUTPUT_KEYS = {
    "aggregated_output",
    "tool_use_result",
    "toolUseResult",
    "stdout",
    "stderr",
}
TOOL_RESULT_TYPES = {"tool_result", "function_call_output"}
TOOL_RESULT_CONTENT_KEYS = {"content", "output"}
TOOL_INPUT_KEYS = {"input", "arguments"}
QUANTITY_KEY = re.compile(r"timeout|limit|max|offset|seconds|_ms$", re.IGNORECASE)
MIMIC_ID_DIGITS = re.compile(r"[123]\d{7}")
EICU_ID_DIGITS = re.compile(r"\d{6,7}")
FORBIDDEN_NAMES = {"output.csv"}
FORBIDDEN_SUFFIXES = {".csv", ".db", ".duckdb", ".parquet", ".pkl"}
ALLOWED_CSV_DIRS = {"metadata"}  # run manifests, not agent outputs
EMAIL_EXEMPT_SUFFIXES = {".patch"}
HASH_MANIFEST = "public_artifact_manifest.json"
PLACEHOLDER = re.compile(r"<REDACTED_[A-Z_]+(?: [^<>]*)?>|<ANON_[A-Z_]+>")
ID_TOKEN = r"(?:MIMIC|EICU)_[A-Z_]*[0-9A-F]{16}"

CONTENT = {
    "credential": re.compile(
        r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}"
        r"|(?<![A-Za-z0-9])rt_[A-Za-z0-9._-]{20,}"
        r"|(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{32,}"
        r"|(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{30,}"
        r"|(?<![A-Za-z0-9])AKIA[0-9A-Z]{16}"
        r"|(?<![A-Za-z0-9])xox[abprs]-[A-Za-z0-9-]{10,}"
        r"|(?<![A-Za-z0-9])hf_[A-Za-z0-9]{30,}"
        r"|Bearer\s+[A-Za-z0-9._~+/=-]{20,}"
        r'|(?:id_token|access_token|refresh_token|client_secret|api_key)"?\s*[:=]\s*"?'
        r"[A-Za-z0-9._~+/=-]{16,}"
    ),
    "mimic_identifier": re.compile(r"(?<![\w.-])[123]\d{7}(?:\.0)?(?![\w-]|\.\d)"),
    "shifted_datetime": re.compile(
        r"(?<![\d.])2[12]\d{2}[-/][01]?\d[-/][0-3]?\d(?!\d)"
        r"|(?:datetime|date|Timestamp)\(\s*['\"]?2[12]\d{2}(?!\d)"
    ),
    "identified_row": re.compile(
        rf"^[ \t]*[(\[|]?[ \t]*['\"]?{ID_TOKEN}['\"]?[ \t]*[,|\t][ \t]*[^\s,|\t]",
        re.MULTILINE,
    ),
    "home_path": re.compile(
        r"/Users/[A-Za-z]|/home/(?!benchagent\b)[A-Za-z]"
        r"|(?<![A-Za-z0-9])-Users-[A-Za-z]|-var-folders-"
    ),
    "email": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    "patient_age": re.compile(
        r"\bage[ds]?\b[ \t]*(?:=|==|:|is|was|of)?[ \t]*\d{1,3}\b"
        r"(?!\.\d|[\d%]|[ \t]*(?:-|\u2013|\+|to\b|and\b|or\b|points?\b|pts?\b))"
        r"|\b\d{1,3}[- ]?(?:years?|yrs?)[- ]old\b",
        re.IGNORECASE,
    ),
}
# eICU stay identifiers have no recognizable shape, so in eICU runs every bare
# 6-7 digit integer counts unless the neighbouring words make it a count.
EICU_BARE_INTEGER = re.compile(r"(?<![\w.,/-])\d{6,7}(?![\w/-]|[.,]\d)")
EICU_COUNT_NEXT = re.compile(
    r"`?[ \t]*(?:(?:data|output|total|distinct|unique|matching|reference|expected)[ \t]+)?"
    r"(?:rows?|records?|keys?|patients|stays|entries|lines|tuples)\b",
    re.IGNORECASE,
)
EICU_COUNT_PREVIOUS = re.compile(
    r"\b(?:rows|count|total)\b[ \t]*(?:[:=]|is|of)?[ \t]*[`'\"(]*$", re.IGNORECASE
)


def expand_escapes(text: str) -> str:
    """Expand JSON escapes at any depth so nested values meet word boundaries."""
    text = re.sub(r"\\+[nrt]", "\n", text)
    return re.sub(r"\\+([\"'/])", r"\1", text)


def lines_of(text: str) -> list[str]:
    return [line for line in text.split("\n") if line.strip()]


class Scan:
    def __init__(self, patterns: dict[str, re.Pattern[str]]):
        self.patterns = patterns
        self.hits: Counter[tuple[str, str]] = Counter()
        self.examples: dict[str, list[str]] = defaultdict(list)
        self.path = Path()

    @property
    def in_eicu_run(self) -> bool:
        return any(part.startswith("eicu-") for part in self.path.parts)

    def hit(self, check: str, count: int = 1) -> None:
        self.hits[(check, self.path.name)] += count
        if len(self.examples[check]) < 5 and str(self.path) not in self.examples[check]:
            self.examples[check].append(str(self.path))

    def text(self, text: str) -> None:
        visible = PLACEHOLDER.sub(" ", expand_escapes(text))
        for name, pattern in self.patterns.items():
            if name == "email" and self.path.suffix in EMAIL_EXEMPT_SUFFIXES:
                continue
            count = len(pattern.findall(visible))
            if count:
                self.hit(name, count)
        if self.in_eicu_run:
            count = sum(
                1
                for match in EICU_BARE_INTEGER.finditer(visible)
                if not EICU_COUNT_NEXT.match(visible, match.end())
                and not EICU_COUNT_PREVIOUS.search(
                    visible, max(0, match.start() - 24), match.start()
                )
            )
            if count:
                self.hit("eicu_identifier", count)

    def value(self, value: Any, key: str = "", in_tool_input: bool = False) -> None:
        if isinstance(value, dict):
            is_tool_result = value.get("type") in TOOL_RESULT_TYPES
            for name, item in value.items():
                if name in TOOL_OUTPUT_KEYS or (
                    is_tool_result and name in TOOL_RESULT_CONTENT_KEYS
                ):
                    if not (
                        isinstance(item, str)
                        and item.startswith("<REDACTED_TOOL_OUTPUT ")
                    ):
                        self.hit("unredacted_tool_output")
                if any(char.isdigit() for char in name):
                    self.text(name)
                self.value(
                    item,
                    name,
                    in_tool_input
                    or (name in TOOL_INPUT_KEYS and isinstance(item, dict | list)),
                )
        elif isinstance(value, list):
            for item in value:
                self.value(item, key, in_tool_input)
        elif isinstance(value, str):
            for nested in self.embedded_events(value):
                self.value(nested)
        elif type(value) in (int, float):  # bool is not an identifier
            if self.is_numeric_identifier(key, value, in_tool_input):
                self.hit("numeric_identifier")

    def is_numeric_identifier(
        self, key: str, value: int | float, in_tool_input: bool
    ) -> bool:
        name = key.lower()
        if name in ID_KEYS or name.removesuffix("s") in ID_KEYS:
            return True
        if not in_tool_input or QUANTITY_KEY.search(name):
            return False
        if not float(value).is_integer():
            return False
        digits = str(int(value))
        return bool(
            MIMIC_ID_DIGITS.fullmatch(digits)
            or (self.in_eicu_run and EICU_ID_DIGITS.fullmatch(digits))
        )

    def embedded_events(self, text: str) -> Iterator[Any]:
        """Yield JSON events embedded line by line in a string; scan the rest."""
        plain = []
        for line in lines_of(text):
            if line.lstrip().startswith("{"):
                try:
                    yield json.loads(line)
                    continue
                except json.JSONDecodeError:
                    pass
            plain.append(line)
        if plain:
            self.text("\n".join(plain))

    def event_stream(self, text: str, *, fragments_allowed: bool) -> None:
        for line in lines_of(text):
            stripped = line.strip()
            if stripped.startswith("{"):
                try:
                    self.value(json.loads(stripped))
                except json.JSONDecodeError:
                    self.hit("malformed_event")
                    self.text(stripped)
                continue
            if not fragments_allowed and (
                '":' in stripped or '\\"' in stripped or stripped[-1] in "}]"
            ):
                if not PLACEHOLDER.fullmatch(stripped):
                    self.hit("event_fragment")
            self.text(stripped)

    def result_json(self, data: Any) -> None:
        agent = data.get("agent_result") if isinstance(data, dict) else None
        if isinstance(agent, dict):
            unparsed = agent.get("unparsed_original_text")
            if unparsed is not None and not str(unparsed).startswith(
                "<REDACTED_UNPARSED_AGENT_RESULT "
            ):
                self.hit("unparsed_agent_result")
            # Here stdout/stderr are the agent CLI's own streams, not tool output.
            stdout = agent.get("stdout")
            if isinstance(stdout, str):
                self.event_stream(stdout, fragments_allowed=False)
            self.value(agent.get("stderr") or "")
            rest = {k: v for k, v in agent.items() if k not in {"stdout", "stderr"}}
            data = {**data, "agent_result": rest}
        self.value(data)

    def file(self, path: Path, root: Path) -> None:
        self.path = path
        in_metadata = bool(ALLOWED_CSV_DIRS & set(path.relative_to(root).parts))
        if path.name in FORBIDDEN_NAMES or (
            path.suffix in FORBIDDEN_SUFFIXES and not in_metadata
        ):
            self.hit("forbidden_file")
            return
        raw = path.read_text(errors="replace")
        if path.suffix == ".jsonl":
            # Harness banner and CLI log lines are plain text; only stdout tails
            # in result.json can hold a truncated event.
            self.event_stream(raw, fragments_allowed=True)
        elif path.suffix == ".json":
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                self.hit("malformed_json")
                self.text(raw)
                return
            if path.name == "result.json":
                self.result_json(data)
            else:
                self.value(data)
        else:
            self.text(raw)


def load_private_patterns(path: Path) -> dict[str, re.Pattern[str]]:
    """Literal and regex entries, from either file format the sanitizer reads."""
    literals: list[str] = []
    regexes: list[str] = []
    if path.suffix == ".json":
        data = json.loads(path.read_text())
        literals = [str(item) for item in data.get("literal", [])]
        regexes = [
            item["pattern"] if isinstance(item, dict) else str(item)
            for item in data.get("regex", [])
        ]
    else:
        for raw_line in path.read_text().splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            kind, _, rest = line.partition(":")
            if kind.lower() == "regex":
                regexes.append(rest.strip())
            elif kind.lower() == "literal":
                literals.append(rest.strip())
            elif kind.lower() != "allow":  # allowed e-mail lines, not terms
                literals.append(line)
    patterns = {
        f"private_literal_{index}": re.compile(
            rf"(?<![A-Za-z0-9]){re.escape(literal)}(?![A-Za-z0-9])", re.IGNORECASE
        )
        for index, literal in enumerate(literals)
        if literal
    }
    for index, regex in enumerate(regexes):
        patterns[f"private_regex_{index}"] = re.compile(regex, re.IGNORECASE)
    return patterns


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("extracted", type=Path)
    parser.add_argument(
        "--private-patterns",
        type=Path,
        help="The sanitizer's private redaction file; its terms and patterns must not appear.",
    )
    args = parser.parse_args()
    patterns = dict(CONTENT)
    if args.private_patterns:
        patterns.update(load_private_patterns(args.private_patterns))

    scan = Scan(patterns)
    files = 0
    for path in sorted(args.extracted.rglob("*")):
        # The hash manifest holds only paths and digests of files scanned here.
        if not path.is_file() or path.name == HASH_MANIFEST:
            continue
        files += 1
        scan.file(path, args.extracted)
    print(f"Scanned {files} files")
    for (check, filename), count in sorted(scan.hits.items()):
        print(f"  {check} in {filename}: {count}")
    for check, examples in sorted(scan.examples.items()):
        print(f"  first files with {check}:")
        for example in examples:
            print(f"    {example}")
    if scan.hits:
        raise SystemExit("Residual private content found.")
    print("No residual private content found.")


if __name__ == "__main__":
    main()
