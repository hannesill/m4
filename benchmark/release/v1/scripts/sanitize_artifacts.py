#!/usr/bin/env python3
"""Public sanitizer for benchmark run artifacts.

This tool keeps rows, code, commands, and run metadata where possible, while
pseudonymizing row identifiers and replacing bulk credentialed-data previews in
traces with structured placeholders. It writes a machine-readable report of
what was changed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import json
import os
import re
import shutil
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import duckdb
except ImportError:  # pragma: no cover - fallback keeps the script stdlib-runnable.
    duckdb = None

M4_DIR = Path(
    os.environ.get("M4BENCH_M4_DIR", Path(__file__).resolve().parents[4])
).resolve()
DEFAULT_PRIVATE_PATTERNS = (
    M4_DIR / "benchmark" / "release" / "v1" / ".private_redactions"
)
DEFAULT_SALT_FILE = M4_DIR / "benchmark" / "release" / "v1" / ".private_sanitize_salt"

TEXT_SUFFIXES = {
    ".json",
    ".jsonl",
    ".log",
    ".md",
    ".py",
    ".sh",
    ".sql",
    ".tex",
    ".txt",
}
CSV_SUFFIXES = {".csv"}
SKIP_SUFFIXES = {
    ".db",
    ".duckdb",
    ".pkl",
    ".pyc",
    ".tmp",
    ".wal",
}
SKIP_NAMES = {".DS_Store"}

ID_COLUMNS = {
    "ab_id": "AB",
    "admissionid": "ADMISSION",
    "hadm_id": "MIMIC_HADM",
    "patienthealthsystemstayid": "EICU_HEALTHSYSTEM_STAY",
    "patientunitstayid": "EICU_UNIT_STAY",
    "person_id": "PERSON",
    "stay_id": "MIMIC_STAY",
    "subject_id": "MIMIC_SUBJECT",
    "uniquepid": "EICU_UNIQUE_PID",
}
SOURCE_LIKE_COLUMNS = {
    "ab_id",
    "age",
    "admissionid",
    "antibiotic",
    "antibiotic_time",
    "charttime",
    "culture_time",
    "endtime",
    "gender",
    "hadm_id",
    "patienthealthsystemstayid",
    "patientunitstayid",
    "positive_culture",
    "specimen",
    "starttime",
    "stay_id",
    "subject_id",
    "suspected_infection_time",
    "uniquepid",
    "weight",
}
PUBLIC_RESULT_COLUMNS = {
    "acidbase_score",
    "admissiontype_score",
    "age_score",
    "aids",
    "aki_stage",
    "aki_stage_crrt",
    "aki_stage_creat",
    "aki_stage_uo",
    "albumin_score",
    "apsiii",
    "bicarbonate_score",
    "bilirubin_score",
    "cardiovascular",
    "cerebrovascular_disease",
    "charlson_comorbidity_index",
    "chronic_pulmonary_disease",
    "ckd",
    "cns",
    "coagulation",
    "comorbidity_score",
    "congestive_heart_failure",
    "creatinine_score",
    "dementia",
    "diabetes_with_cc",
    "diabetes_without_cc",
    "electivesurgery_score",
    "gcs_eyes",
    "gcs_min",
    "gcs_motor",
    "gcs_score",
    "gcs_verbal",
    "glucose_score",
    "heart_rate_score",
    "hematocrit_score",
    "hr_score",
    "liver",
    "malignant_cancer",
    "mbp_score",
    "mdrd_est",
    "mechvent_score",
    "meld",
    "metastatic_solid_tumor",
    "mild_liver_disease",
    "myocardial_infarct",
    "norepinephrine_equivalent_dose",
    "oasis",
    "pao2_aado2_score",
    "pao2fio2_score",
    "paraplegia",
    "peptic_ulcer_disease",
    "peripheral_vascular_disease",
    "potassium_score",
    "preiculos_score",
    "renal",
    "renal_disease",
    "resp_rate_score",
    "resp_score",
    "respiration",
    "rheumatic_disease",
    "sapsii",
    "scr_baseline",
    "sepsis3",
    "severe_liver_disease",
    "sirs",
    "sofa",
    "sofa_score",
    "sodium_score",
    "suspected_infection",
    "sysbp_score",
    "temp_score",
    "uo_mlkghr_12hr",
    "uo_mlkghr_24hr",
    "uo_mlkghr_6hr",
    "uo_score",
    "uo_tm_12hr",
    "uo_tm_24hr",
    "uo_tm_6hr",
    "urineoutput_score",
    "vent_status",
    "ventilation_seq",
    "ventilation_status",
    "wbc_score",
}
TIME_COLUMN_PATTERNS = (
    "time",
    "date",
    "charttime",
    "starttime",
    "endtime",
    "intime",
    "outtime",
    "offset",
)
DATA_TERMS = {
    "ab_id",
    "admissionid",
    "antibiotic_time",
    "charttime",
    "culture_time",
    "endtime",
    "hadm_id",
    "intime",
    "labresultoffset",
    "nursingchartoffset",
    "outtime",
    "patienthealthsystemstayid",
    "patientunitstayid",
    "sofa_time",
    "starttime",
    "stay_id",
    "subject_id",
    "suspected_infection_time",
    "uniquepid",
}
RESULT_JSON_TEXT_PATHS = {
    ("agent_result", "stderr"),
    ("test_results", "pytest_output"),
    ("test_results", "pytest_stderr"),
}
# Agent CLI stdout is a tail of the JSON event stream, so its first line can be
# a truncated event whose tool output cannot be separated from agent text.
RESULT_JSON_EVENT_STREAM_PATH = ("agent_result", "stdout")
# Written by repair_result_json.py for malformed historical result.json: the
# verbatim malformed block, in which tool output cannot be located at all.
RESULT_JSON_UNPARSED_PATH = ("agent_result", "unparsed_original_text")


@dataclass
class PrivatePatterns:
    literals: list[str] = field(default_factory=list)
    regexes: list[re.Pattern[str]] = field(default_factory=list)
    allow: list[str] = field(default_factory=list)


@dataclass
class SanitizerConfig:
    salt: bytes
    private_patterns: PrivatePatterns
    csv_mode: str = "scores-only"
    time_mode: str = "offset-hours"
    copy_binary: bool = False
    include_row_key_hash: bool = False
    collect_input_hashes: bool = True


@dataclass
class FileReport:
    path: str
    action: str
    input_size_bytes: int
    output_size_bytes: int = 0
    input_sha256: str = ""
    output_sha256: str = ""
    rows: int = 0
    transformed_columns: list[str] = field(default_factory=list)
    redacted_blocks: int = 0
    redacted_terms: int = 0
    redacted_secrets: int = 0
    withheld_unparseable: int = 0
    remaining_at_signs: int = 0
    kept_columns: list[str] = field(default_factory=list)
    dropped_columns: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class SanitizationReport:
    source: str
    output: str
    files: list[FileReport] = field(default_factory=list)
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )
    private_patterns_loaded: bool = False
    private_literal_patterns: int = 0
    private_regex_patterns: int = 0
    skipped_files: int = 0

    def to_json(self, *, include_private_details: bool = False) -> dict[str, Any]:
        actions = Counter(item.action for item in self.files)
        transformed_columns: dict[str, int] = defaultdict(int)
        dropped_columns: dict[str, int] = defaultdict(int)
        for item in self.files:
            for column in item.transformed_columns:
                transformed_columns[column] += 1
            for column in item.dropped_columns:
                dropped_columns[column] += 1
        files = []
        for item in self.files:
            record = dict(item.__dict__)
            if not include_private_details:
                record.pop("input_sha256", None)
            files.append(record)

        data = {
            "description": "Sanitization report.",
            "started_at": self.started_at,
            "finished_at": datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "source": "<SANITIZED_SOURCE_PATH>",
            "output": "<SANITIZED_OUTPUT_PATH>",
            "private_redaction_patterns": {
                "loaded": self.private_patterns_loaded,
                "literal_count": self.private_literal_patterns,
                "regex_count": self.private_regex_patterns,
                "note": "Pattern text, source paths, and hashes are intentionally omitted.",
            },
            "salt": {
                "loaded": True,
                "note": "The HMAC salt is intentionally omitted and must not be published.",
            },
            "summary": {
                "files": len(self.files),
                "actions": dict(sorted(actions.items())),
                "skipped_files": self.skipped_files,
                "csv_rows_processed": sum(item.rows for item in self.files),
                "redacted_trace_blocks": sum(
                    item.redacted_blocks for item in self.files
                ),
                "redacted_private_terms": sum(
                    item.redacted_terms for item in self.files
                ),
                "redacted_secrets": sum(item.redacted_secrets for item in self.files),
                "withheld_unparseable_events": sum(
                    item.withheld_unparseable for item in self.files
                ),
                "remaining_at_signs": sum(
                    item.remaining_at_signs for item in self.files
                ),
                "transformed_columns": dict(sorted(transformed_columns.items())),
                "dropped_columns": dict(sorted(dropped_columns.items())),
            },
            "notes": [
                "Tool and command outputs in traces are replaced with structured placeholders.",
                "Events that are not valid JSON in the source are withheld whole, because their tool output cannot be separated from agent text.",
            ],
            "files": files,
        }
        if include_private_details:
            data["source"] = self.source
            data["output"] = self.output
            data["private_report_details"] = {
                "included": True,
                "note": "This report includes absolute paths and input hashes; do not publish it.",
            }
        return data


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_salt(args: argparse.Namespace) -> bytes:
    if args.salt:
        return args.salt.encode("utf-8")
    if args.salt_file:
        salt_path = args.salt_file.expanduser()
    else:
        env_salt_file = os.environ.get("M4BENCH_SANITIZE_SALT_FILE")
        salt_path = (
            Path(env_salt_file).expanduser() if env_salt_file else DEFAULT_SALT_FILE
        )
    if salt_path.is_file():
        salt = salt_path.read_bytes().strip()
        if salt:
            return salt
    env_salt = os.environ.get("M4BENCH_SANITIZE_SALT")
    if env_salt:
        return env_salt.encode("utf-8")
    if args.allow_insecure_salt:
        return b"INSECURE-TEST-SALT-DO-NOT-USE-FOR-PUBLIC-ARTIFACTS"
    raise SystemExit(
        "No private sanitize salt found. Set M4BENCH_SANITIZE_SALT, "
        "M4BENCH_SANITIZE_SALT_FILE, --salt, or --salt-file. Use "
        "--allow-insecure-salt only for tests or dry-run examples."
    )


def load_private_patterns(path: Path | None) -> PrivatePatterns:
    patterns = PrivatePatterns()
    if path is None:
        env_path = os.environ.get("M4BENCH_PRIVATE_REDACTIONS")
        path = Path(env_path).expanduser() if env_path else DEFAULT_PRIVATE_PATTERNS
    if not path.exists():
        return patterns

    if path.suffix == ".json":
        data = json.loads(path.read_text())
        patterns.literals.extend(str(item) for item in data.get("literal", []))
        patterns.allow.extend(str(item) for item in data.get("allow", []))
        for item in data.get("regex", []):
            expr = item["pattern"] if isinstance(item, dict) else str(item)
            patterns.regexes.append(re.compile(expr, flags=re.IGNORECASE))
        return patterns

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        lower = line.lower()
        if lower.startswith("literal:"):
            patterns.literals.append(line.split(":", 1)[1].strip())
        elif lower.startswith("regex:"):
            patterns.regexes.append(
                re.compile(line.split(":", 1)[1].strip(), flags=re.IGNORECASE)
            )
        elif lower.startswith("allow:"):
            patterns.allow.append(line.split(":", 1)[1].strip())
        else:
            patterns.literals.append(line)
    return patterns


def pseudonymize(value: str, *, prefix: str, salt: bytes) -> str:
    stripped = value.strip()
    if stripped == "" or stripped.lower() in {"nan", "none", "null", "na"}:
        return value
    digest = (
        hmac.new(
            salt,
            f"{prefix}:{stripped}".encode(),
            hashlib.sha256,
        )
        .hexdigest()[:16]
        .upper()
    )
    return f"{prefix}_{digest}"


def is_time_column(column: str) -> bool:
    lower = column.lower()
    if lower in ID_COLUMNS:
        return False
    return any(term in lower for term in TIME_COLUMN_PATTERNS)


def parse_datetime(value: str) -> datetime | None:
    text = value.strip()
    if not text or text.lower() in {"nan", "none", "null", "na"}:
        return None
    if re.fullmatch(r"[-+]?\d+(\.\d+)?", text):
        return None
    normalized = text.replace("Z", "+00:00")
    for candidate in (normalized, normalized.replace(" ", "T", 1)):
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None


def row_anchor(row: dict[str, str]) -> str:
    for column in (
        "stay_id",
        "patientunitstayid",
        "hadm_id",
        "patienthealthsystemstayid",
        "subject_id",
        "uniquepid",
    ):
        value = row.get(column)
        if value:
            return f"{column}:{value}"
    return "__file__"


def row_key_hash(row: dict[str, str], *, salt: bytes) -> str:
    parts = []
    for column in (
        "subject_id",
        "hadm_id",
        "stay_id",
        "patientunitstayid",
        "uniquepid",
        "patienthealthsystemstayid",
        "ab_id",
    ):
        value = row.get(column)
        if value:
            parts.append(f"{column}={value}")
    if not parts:
        parts = [f"{key}={row.get(key, '')}" for key in sorted(row)]
    digest = hmac.new(salt, "|".join(parts).encode(), hashlib.sha256).hexdigest()
    return f"ROWKEY_{digest[:20].upper()}"


def is_public_result_column(column: str) -> bool:
    lower = column.lower()
    if lower in SOURCE_LIKE_COLUMNS or is_time_column(lower):
        return False
    if lower in PUBLIC_RESULT_COLUMNS:
        return True
    if lower.endswith("_score"):
        return True
    if lower.endswith("_stage"):
        return True
    return False


def sanitize_time(
    value: str,
    *,
    anchor: str,
    anchors: dict[str, datetime],
    config: SanitizerConfig,
) -> tuple[str, str | None]:
    if config.time_mode == "keep":
        return value, None
    parsed = parse_datetime(value)
    if parsed is None:
        if not value.strip() or re.fullmatch(r"[-+]?\d+(\.\d+)?", value.strip()):
            return value, None
        return "<TIME_UNPARSED>", "unparsed_time"
    if config.time_mode == "date":
        return parsed.strftime("%Y-%m-%d"), None
    base = anchors.setdefault(anchor, parsed)
    hours = (parsed - base).total_seconds() / 3600.0
    return f"{hours:+.3f}h", None


def redact_private_text(
    text: str,
    patterns: PrivatePatterns,
) -> tuple[str, int]:
    redacted = text
    count = 0
    for literal in sorted(patterns.literals, key=len, reverse=True):
        if not literal:
            continue
        new, n = re.subn(re.escape(literal), "<REDACTED_PRIVATE>", redacted)
        redacted = new
        count += n
    for pattern in patterns.regexes:
        redacted, n = pattern.subn("<REDACTED_PRIVATE_REGEX>", redacted)
        count += n
    return redacted, count


# Path characters stop at backslashes as well as quotes and whitespace. Traces
# and agent stdout embed JSON-escaped text, so a path followed by an escaped
# quote (`\"`) must not consume the escape; doing so produced the malformed
# result.json files in the original review archive.
LOCAL_PATH_PATTERNS = (
    (re.compile(r"/Users/[^\s\"'\\]+"), "<ANON_LOCAL_PATH>"),
    (re.compile(r"/home/[^\s\"'\\]+"), "<ANON_LOCAL_PATH>"),
    (re.compile(r"/var/folders/[^\s\"'\\]+"), "<ANON_TMP_PATH>"),
    # Claude Code names project directories after the host path with slashes
    # turned into dashes (`~/.claude/projects/-Users-name-repo`).
    (re.compile(r"-var-folders-[A-Za-z0-9_-]+"), "<ANON_TMP_PATH>"),
    (re.compile(r"(?<![A-Za-z0-9])-Users-[A-Za-z0-9_.-]+"), "<ANON_LOCAL_PATH>"),
)


def redact_local_paths(text: str) -> str:
    for pattern, replacement in LOCAL_PATH_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


# Trace and stdout text is often JSON-escaped one or more times, so a value can
# directly follow an escaped newline or tab (`\n`, `\t`). The character before
# it is then a letter and a plain word boundary does not match.
AFTER_ESCAPE = r"(?<=\\[nrt])"

# Agents sometimes print credential files (for example `.codex/auth.json`)
# while exploring the container, so secrets are removed wherever they appear.
SECRET_TOKEN = re.compile(
    r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}(?:\.[A-Za-z0-9_-]+)?"  # JWT
    rf"|(?:\b|{AFTER_ESCAPE})(?:"
    r"rt_[A-Za-z0-9._-]{20,}"  # OpenAI refresh token
    r"|sk-(?:ant-|proj-|svcacct-)?[A-Za-z0-9_-]{32,}"  # OpenAI/Anthropic API key
    r"|gh[pousr]_[A-Za-z0-9]{30,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|xox[abprs]-[A-Za-z0-9-]{10,}"
    r"|hf_[A-Za-z0-9]{30,}"
    r"|Bearer\s+[A-Za-z0-9._~+/=-]{20,}"
    r")"
)
# `\\*"` accepts the quote at any JSON-escaping depth.
SECRET_FIELD = re.compile(
    r"(?P<key>(?:id_token|access_token|refresh_token|api_key|apikey|client_secret"
    r"|session_token|session_key|authorization|account_id|chatgpt_account_id"
    r'|chatgpt_user_id|installation_id)\\*"\s*:\s*\\*")(?P<value>[^"\\]{8,})',
    flags=re.IGNORECASE,
)


def redact_secrets(text: str) -> tuple[str, int]:
    text, fields = SECRET_FIELD.subn(r"\g<key><REDACTED_SECRET>", text)
    text, tokens = SECRET_TOKEN.subn("<REDACTED_SECRET>", text)
    return text, fields + tokens


def keyed_digest(text: str, salt: bytes) -> str:
    """Salted digest prefix: short redacted values cannot be brute-forced."""
    return hmac.new(salt, text.encode("utf-8"), hashlib.sha256).hexdigest()[:16]


def sanitize_text_basic(
    text: str,
    *,
    config: SanitizerConfig,
    report: FileReport,
    scan_private_patterns: bool = True,
) -> str:
    if scan_private_patterns:
        redacted, n = redact_private_text(text, config.private_patterns)
        report.redacted_terms += n
    else:
        redacted = text
    redacted, secrets = redact_secrets(redacted)
    report.redacted_secrets += secrets
    redacted = re.sub(
        r'("signature"\s*:\s*")[^"]+(")',
        r"\1<REDACTED_SIGNATURE>\2",
        redacted,
    )
    redacted = re.sub(
        r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        "<REDACTED_EMAIL>",
        redacted,
        flags=re.IGNORECASE,
    )
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
    redacted = redact_local_paths(redacted)
    redacted = redact_named_ids(redacted, config.salt)
    report.remaining_at_signs += count_remaining_at_signs(
        redacted,
        allow=config.private_patterns.allow,
    )
    return redacted


def redact_named_ids(text: str, salt: bytes) -> str:
    id_names = "|".join(
        re.escape(name) for name in sorted(ID_COLUMNS, key=len, reverse=True)
    )
    # Values must be numeric identifiers. After a comma only long values count,
    # so SQL column lists (`stay_id, t1.subject_id`) and `ORDER BY stay_id, 1`
    # stay intact. A trailing `.0` covers identifiers printed as floats.
    pattern = re.compile(
        rf"\b(?P<name>{id_names})\b(?P<sep>\s*[:=]\s*['\"]?|\s*,\s*['\"]?(?=\d{{5}}|0\d\d-))"
        r"(?P<value>\d[\d-]*(?:\.0)?)(?![\w.])",
        flags=re.IGNORECASE,
    )

    def replace(match: re.Match[str]) -> str:
        prefix = ID_COLUMNS[match.group("name").lower()]
        value = match.group("value").removesuffix(".0")
        return f"{match.group('name')}{match.group('sep')}{pseudonymize(value, prefix=prefix, salt=salt)}"

    return pattern.sub(replace, text)


def count_remaining_at_signs(text: str, *, allow: list[str]) -> int:
    count = 0
    for line in text.splitlines():
        if "@" not in line:
            continue
        if any(term and term in line for term in allow):
            continue
        count += line.count("@")
    return count


def data_term_count(line: str) -> int:
    lower = line.lower()
    return sum(1 for term in DATA_TERMS if term in lower)


def looks_like_table_header(line: str) -> bool:
    lower = line.lower()
    if re.search(r"\b(select|from|where|join|def|class|import|with|return)\b", lower):
        return False
    if "=" in line or any(quote in line for quote in ("'", '"')):
        return False
    if data_term_count(line) < 2:
        return False
    return any(sep in line for sep in (",", "|", "\t")) or len(line.split()) >= 4


# A field that holds a value: a number, or an identifier or datetime that was
# already replaced. Column names with digits (`uo_tm_6hr`) are not values, so a
# column list that wraps over several lines is not mistaken for rows.
VALUE_FIELD = re.compile(
    r"^\W*(?:[-+]?\d[\d.,:eE+-]*%?"
    r"|(?:MIMIC|EICU|AB|PERSON|ADMISSION)_[A-Z_]*[0-9A-F]{16}"
    r"|<REDACTED_[A-Z_]+>)\W*$"
)


def looks_like_table_row(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if any(sep in stripped for sep in (",", "|", "\t")):
        parts = re.split(r"[,|\t]", stripped)
        values = sum(1 for part in parts if VALUE_FIELD.match(part))
        return len(parts) >= 3 and values >= 2
    parts = stripped.split()
    values = sum(1 for part in parts if VALUE_FIELD.match(part))
    return len(parts) >= 4 and values >= 2


# A row quoted in agent prose after scrubbing: it starts with a pseudonymized
# identifier or a redacted datetime and continues with at least one more
# delimited field. Two columns are enough: `30012345,76` is a patient's age.
IDENTIFIED_ROW = re.compile(
    r"^\s*[(\[|]?\s*['\"]?"
    r"(?:(?:MIMIC|EICU)_[A-Z_]+_[0-9A-F]{16}|<REDACTED_SHIFTED_DATETIME>)"
    r"['\"]?\s*(?:[,|\t]|\s{2,})\s*\S"
)


def looks_like_identified_row(line: str) -> bool:
    return bool(IDENTIFIED_ROW.match(line))


def redact_trace_data_blocks(
    text: str,
    *,
    config: SanitizerConfig,
    report: FileReport,
) -> str:
    lines = text.splitlines(keepends=True)
    out: list[str] = []

    def placeholder(kind: str, block: list[str]) -> str:
        block_text = "".join(block)
        columns = sorted(term for term in DATA_TERMS if term in block_text.lower())
        report.redacted_blocks += 1
        return (
            "<REDACTED_DATA_BLOCK "
            f'type="{kind}" lines="{len(block)}" '
            f'columns="{",".join(columns[:20])}" '
            f'hmac_prefix="{keyed_digest(block_text, config.salt)}">\n'
        )

    i = 0
    while i < len(lines):
        line = lines[i]
        if looks_like_table_header(line):
            end = i + 1
            while end < len(lines) and looks_like_table_row(lines[end]):
                end += 1
            # A column list without rows is a schema, SQL, or instruction line.
            if end > i + 1:
                out.append(placeholder("tabular_preview", lines[i:end]))
                i = end
                continue
        if looks_like_identified_row(line):
            end = i + 1
            while end < len(lines) and looks_like_identified_row(lines[end]):
                end += 1
            out.append(placeholder("identified_rows", lines[i:end]))
            i = end
            continue
        out.append(line)
        i += 1
    return "".join(out)


def sql_string(value: Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def sql_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def try_sanitize_scores_only_output_csv_fast(
    source: Path,
    dest: Path,
    *,
    report: FileReport,
    fieldnames: list[str],
    kept_source_columns: list[str],
) -> bool:
    if duckdb is None:
        return False

    output_fieldnames = ["row_id", *kept_source_columns]
    report.kept_columns = output_fieldnames
    report.dropped_columns = [
        column for column in fieldnames if column not in kept_source_columns
    ]
    select_columns = "".join(
        f", {sql_identifier(column)}" for column in kept_source_columns
    )
    query = f"""
        COPY (
          SELECT printf('row_%06d', row_number() OVER ()) AS row_id{select_columns}
          FROM read_csv_auto({sql_string(source)}, all_varchar=true, header=true)
        ) TO {sql_string(dest)} (HEADER, DELIMITER ',');
    """
    try:
        result = duckdb.connect(":memory:").execute(query)
        row = result.fetchone()
        report.rows = int(row[0]) if row else 0
        finish_file_report(dest, report)
        return True
    except Exception as exc:  # pragma: no cover - exercised only on parser fallback.
        report.warnings.append(f"duckdb_csv_fast_path_failed:{type(exc).__name__}")
        if dest.exists():
            dest.unlink()
        return False


def sanitize_csv_file(
    source: Path,
    dest: Path,
    *,
    rel_path: Path,
    config: SanitizerConfig,
) -> FileReport:
    report = base_file_report(
        source,
        rel_path,
        "csv_sanitized",
        collect_input_hash=config.collect_input_hashes,
    )
    anchors: dict[str, datetime] = {}
    dest.parent.mkdir(parents=True, exist_ok=True)
    csv_mode = config.csv_mode
    if csv_mode == "scores-only" and source.name != "output.csv":
        csv_mode = "pseudonymized-full"

    with source.open("r", encoding="utf-8", errors="replace", newline="") as src:
        sample = src.read(4096)
        src.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample)
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(src, dialect=dialect)
        if reader.fieldnames is None:
            dest.write_text("", encoding="utf-8")
            finish_file_report(dest, report)
            return report
        fieldnames = list(reader.fieldnames)
        if csv_mode == "scores-only":
            kept_source_columns = [
                column for column in fieldnames if is_public_result_column(column)
            ]
            output_fieldnames = ["row_id"]
            if config.include_row_key_hash:
                output_fieldnames.append("row_key_hash")
                report.transformed_columns.append("row_key_hash")
            output_fieldnames.extend(kept_source_columns)
            report.kept_columns = output_fieldnames
            report.dropped_columns = [
                column for column in fieldnames if column not in kept_source_columns
            ]
            if (
                source.name == "output.csv"
                and not config.include_row_key_hash
                and try_sanitize_scores_only_output_csv_fast(
                    source,
                    dest,
                    report=report,
                    fieldnames=fieldnames,
                    kept_source_columns=kept_source_columns,
                )
            ):
                return report

            with dest.open("w", encoding="utf-8", newline="") as dst:
                writer = csv.DictWriter(
                    dst, fieldnames=output_fieldnames, dialect=dialect
                )
                writer.writeheader()
                for index, row in enumerate(reader, start=1):
                    report.rows += 1
                    out_row = {"row_id": f"row_{index:06d}"}
                    if config.include_row_key_hash:
                        out_row["row_key_hash"] = row_key_hash(row, salt=config.salt)
                    for column in kept_source_columns:
                        out_row[column] = row.get(column, "")
                    writer.writerow(out_row)
            finish_file_report(dest, report)
            return report

        transformed = []
        for column in fieldnames:
            lower = column.lower()
            if lower in ID_COLUMNS or is_time_column(lower):
                transformed.append(column)
        report.transformed_columns = transformed
        report.kept_columns = fieldnames

        with dest.open("w", encoding="utf-8", newline="") as dst:
            writer = csv.DictWriter(dst, fieldnames=fieldnames, dialect=dialect)
            writer.writeheader()
            for row in reader:
                report.rows += 1
                original_anchor = row_anchor(row)
                out_row = dict(row)
                for column in fieldnames:
                    value = out_row.get(column, "")
                    lower = column.lower()
                    if lower in ID_COLUMNS:
                        out_row[column] = pseudonymize(
                            value,
                            prefix=ID_COLUMNS[lower],
                            salt=config.salt,
                        )
                    elif is_time_column(lower):
                        sanitized, warning = sanitize_time(
                            value,
                            anchor=original_anchor,
                            anchors=anchors,
                            config=config,
                        )
                        out_row[column] = sanitized
                        if warning:
                            report.warnings.append(f"{column}:{warning}")
                    elif isinstance(value, str):
                        if source.name == "output.csv":
                            continue
                        text_report = FileReport(
                            path=report.path,
                            action="embedded_text",
                            input_size_bytes=0,
                        )
                        out_row[column] = sanitize_text_basic(
                            value,
                            config=config,
                            report=text_report,
                            scan_private_patterns=False,
                        )
                        report.redacted_terms += text_report.redacted_terms
                        report.remaining_at_signs += text_report.remaining_at_signs
                writer.writerow(out_row)

    report.warnings = sorted(set(report.warnings))[:50]
    finish_file_report(dest, report)
    return report


def sanitize_json_file(
    source: Path,
    dest: Path,
    *,
    rel_path: Path,
    config: SanitizerConfig,
) -> FileReport:
    report = base_file_report(
        source,
        rel_path,
        "json_sanitized",
        collect_input_hash=config.collect_input_hashes,
    )
    raw = source.read_text(encoding="utf-8", errors="replace")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        sanitized = sanitize_text_payload(raw, config=config, report=report)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(sanitized, encoding="utf-8")
        finish_file_report(dest, report)
        return report

    sanitized_data = sanitize_json_value(data, (), config=config, report=report)
    payload = json.dumps(sanitized_data, indent=2, sort_keys=True) + "\n"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(payload, encoding="utf-8")
    finish_file_report(dest, report)
    return report


def sanitize_json_value(
    value: Any,
    path: tuple[str, ...],
    *,
    config: SanitizerConfig,
    report: FileReport,
) -> Any:
    if isinstance(value, dict):
        return {
            key: sanitize_json_value(
                item, (*path, str(key)), config=config, report=report
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            sanitize_json_value(item, (*path, str(index)), config=config, report=report)
            for index, item in enumerate(value)
        ]
    if isinstance(value, str):
        lower_key = path[-1].lower() if path else ""
        if lower_key == "sha256" or lower_key.endswith("_sha256"):
            report.transformed_columns.append(path[-1])
            return "<REDACTED_SOURCE_HASH>"
        if lower_key in ID_COLUMNS and re.search(r"\d", value):
            report.transformed_columns.append(path[-1])
            return pseudonymize(value, prefix=ID_COLUMNS[lower_key], salt=config.salt)
        if path[-2:] == RESULT_JSON_UNPARSED_PATH:
            report.withheld_unparseable += 1
            return (
                f'<REDACTED_UNPARSED_AGENT_RESULT chars="{len(value)}" '
                f'hmac_prefix="{keyed_digest(value, config.salt)}">'
            )
        if path[-2:] == RESULT_JSON_EVENT_STREAM_PATH:
            return sanitize_text_payload(
                value, config=config, report=report, event_stream=True
            )
        if any(path[-len(item) :] == item for item in RESULT_JSON_TEXT_PATHS):
            return sanitize_text_payload(value, config=config, report=report)
        return sanitize_text_basic(value, config=config, report=report)
    if isinstance(value, int) and path:
        lower_key = path[-1].lower()
        if lower_key in ID_COLUMNS:
            report.transformed_columns.append(path[-1])
            return pseudonymize(
                str(value), prefix=ID_COLUMNS[lower_key], salt=config.salt
            )
    return value


# Keys whose values are tool/command output (database query results, file
# reads) in Claude Code and Codex traces. Agent-authored content (messages,
# SQL, code, tool inputs) is kept; tool output is replaced by a placeholder
# because it can contain row-level credentialed data inside JSON strings,
# where the line-based data-block detector cannot see it.
TOOL_OUTPUT_KEYS = {
    "toolUseResult",
    "tool_use_result",
    "aggregated_output",
    "stdout",
    "stderr",
}
TOOL_RESULT_TYPES = {"tool_result", "function_call_output"}
TOOL_RESULT_CONTENT_KEYS = {"content", "output"}
# Dates are shifted into 2100-2299. Python reprs (`datetime.date(2150, 1, 2)`)
# and dates without zero padding are covered as well as ISO text.
SHIFTED_DATETIME = re.compile(
    rf"(?:\b|{AFTER_ESCAPE})"
    r"2[12]\d\d-[01]?\d-[0-3]?\d(?:[ T][0-2]\d:[0-5]\d(?::[0-5]\d(?:\.\d+)?)?)?"
    r"|(?:datetime\.)?(?:datetime|date)\(2[12]\d\d(?:,\s*\d+)*\)"
)
# MIMIC-IV subject/hadm/stay identifiers are 8-digit integers starting 1/2/3,
# sometimes printed as floats (`30012345.0`). Word, hyphen, and decimal guards
# keep run-id timestamps, UUID segments, and float digits intact.
MIMIC_IDENTIFIER = re.compile(
    rf"(?:(?<![\w.-])|{AFTER_ESCAPE})[123]\d{{7}}(?:\.0)?(?![\w-]|\.\d)"
)
# eICU `uniquepid` values look like `000-12345`.
EICU_UNIQUE_PID = re.compile(
    rf"(?:(?<![\w.-])|{AFTER_ESCAPE})0[0-3]\d-\d{{3,6}}(?![\w-])"
)
PATIENT_AGE = re.compile(r"(?<![\w.])\d{1,3}(?=[- ]?(?:year|yr)s?[- ]old\b)")
# Ages stated as a value (`age = 70`, `age of 52`, `aged 70`). Ranges, decimals,
# and comparisons (`ages 75-80`, `age 5.73`, `age >= 16`) describe rules or
# aggregates and are kept.
PATIENT_AGE_VALUE = re.compile(
    r"(?P<lead>\b(?:age[sd]?)\b[ \t]*(?:==?|:|is|was|of)?[ \t]*)(?P<value>\d{1,3})"
    r"(?![\d%]|\.\d|[ \t]*(?:[-\u2013+]|to\b|and\b|or\b|points?\b|pts?\b))",
    re.IGNORECASE,
)
# eICU stay identifiers are 6-7 digit integers with no fixed leading digit, so
# they cannot be told apart from other numbers by shape. In eICU runs every
# standalone integer of six to nine digits is pseudonymized unless the text
# next to it on the same line marks it as a count. Fractions, decimals, and
# digit groups stay.
EICU_INTEGER = re.compile(
    rf"(?:(?<![\w.,/-])|{AFTER_ESCAPE})\d{{6,9}}(?![\w/-]|[.,]\d)"
)
COUNT_AFTER = re.compile(
    r"`?[ \t]*(?:(?:data|output|total|distinct|unique|matching|reference|expected)[ \t]+)?"
    r"(?:rows?|records?|keys?|patients|stays|entries|lines|tuples)\b",
    re.IGNORECASE,
)
COUNT_BEFORE = re.compile(
    r"\b(?:rows|count|total)\b[ \t]*(?:[:=]|is|of)?[ \t]*[`'\"(]*$", re.IGNORECASE
)
REDACTION_PLACEHOLDER = re.compile(r"<REDACTED_[A-Z_]+[^<>]*>")


def is_eicu_run(path: str) -> bool:
    return any(part.startswith("eicu-") for part in Path(path).parts)


def pseudonymize_eicu_integers(text: str, salt: bytes) -> tuple[str, int]:
    protected = [m.span() for m in REDACTION_PLACEHOLDER.finditer(text)]
    count = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal count
        start, end = match.span()
        if any(a <= start < b for a, b in protected):
            return match.group(0)
        if COUNT_AFTER.match(text, end) or COUNT_BEFORE.search(
            text, max(0, start - 24), start
        ):
            return match.group(0)
        count += 1
        return pseudonymize(match.group(0), prefix="EICU_ID", salt=salt)

    return EICU_INTEGER.sub(replace, text), count


def pseudonymize_bare_identifiers(text: str, salt: bytes) -> tuple[str, int]:
    text, mimic = MIMIC_IDENTIFIER.subn(
        lambda match: pseudonymize(
            match.group(0).removesuffix(".0"), prefix="MIMIC_ID", salt=salt
        ),
        text,
    )
    text, eicu = EICU_UNIQUE_PID.subn(
        lambda match: pseudonymize(
            match.group(0), prefix=ID_COLUMNS["uniquepid"], salt=salt
        ),
        text,
    )
    return text, mimic + eicu


def tool_output_placeholder(value: Any, salt: bytes) -> str:
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    return (
        f'<REDACTED_TOOL_OUTPUT chars="{len(text)}" '
        f'hmac_prefix="{keyed_digest(text, salt)}">'
    )


def redact_tool_outputs(value: Any, report: FileReport, salt: bytes) -> Any:
    if isinstance(value, list):
        return [redact_tool_outputs(item, report, salt) for item in value]
    if not isinstance(value, dict):
        return value
    is_tool_result = value.get("type") in TOOL_RESULT_TYPES
    redacted = {}
    for key, item in value.items():
        if key in TOOL_OUTPUT_KEYS or (
            is_tool_result and key in TOOL_RESULT_CONTENT_KEYS
        ):
            redacted[key] = tool_output_placeholder(item, salt)
            report.redacted_blocks += 1
        else:
            redacted[key] = redact_tool_outputs(item, report, salt)
    return redacted


# Structured tool input (Claude `tool_use.input`, Codex `mcp_tool_call.arguments`).
TOOL_INPUT_KEYS = {"input", "arguments"}
# Tool input keys whose numbers are durations or limits, never identifiers.
QUANTITY_KEY = re.compile(r"timeout|limit|max|offset|seconds|_ms$", re.IGNORECASE)


def numeric_identifier_prefix(
    key: str, value: int | float, *, in_tool_input: bool, eicu: bool
) -> str | None:
    """The pseudonym prefix for a JSON number that is an identifier, else None."""
    name = key.lower()
    prefix = ID_COLUMNS.get(name) or ID_COLUMNS.get(name.removesuffix("s"))
    if prefix:
        return prefix
    # In tool input the agent chooses the keys (`ids`, `stays`), so there a
    # number with an identifier's shape counts whatever its key. Elsewhere such
    # numbers are byte counts, token counters and seeds.
    if not in_tool_input or QUANTITY_KEY.search(name):
        return None
    if isinstance(value, float) and not value.is_integer():
        return None
    digits = str(int(value))
    if MIMIC_IDENTIFIER.fullmatch(digits):
        return "MIMIC_ID"
    if eicu and EICU_INTEGER.fullmatch(digits):
        return "EICU_ID"
    return None


def sanitize_event_strings(
    value: Any,
    *,
    config: SanitizerConfig,
    report: FileReport,
    key: str = "",
    in_tool_input: bool = False,
) -> Any:
    if isinstance(value, dict):
        return {
            name: sanitize_event_strings(
                item,
                config=config,
                report=report,
                key=name,
                in_tool_input=in_tool_input
                or (name in TOOL_INPUT_KEYS and isinstance(item, dict | list)),
            )
            for name, item in value.items()
        }
    if isinstance(value, list):
        return [
            sanitize_event_strings(
                item,
                config=config,
                report=report,
                key=key,
                in_tool_input=in_tool_input,
            )
            for item in value
        ]
    if key == "signature" and isinstance(value, str):
        return "<REDACTED_SIGNATURE>"  # opaque model-provider blob
    if isinstance(value, str):
        return redact_trace_data_blocks(
            scrub_record_values(value, config=config, report=report),
            config=config,
            report=report,
        )
    if type(value) not in (int, float):  # bool is not an identifier
        return value
    prefix = numeric_identifier_prefix(
        key, value, in_tool_input=in_tool_input, eicu=is_eicu_run(report.path)
    )
    if prefix is None:
        return value
    report.redacted_terms += 1
    return pseudonymize(str(value).removesuffix(".0"), prefix=prefix, salt=config.salt)


def scrub_record_values(
    text: str, *, config: SanitizerConfig, report: FileReport
) -> str:
    """Basic redaction plus shifted datetimes, bare identifiers, and ages."""
    text = sanitize_text_basic(text, config=config, report=report)
    text, dates = SHIFTED_DATETIME.subn("<REDACTED_SHIFTED_DATETIME>", text)
    text, identifiers = pseudonymize_bare_identifiers(text, config.salt)
    if is_eicu_run(report.path):
        text, eicu = pseudonymize_eicu_integers(text, config.salt)
        identifiers += eicu
    text, ages = PATIENT_AGE.subn("<REDACTED_AGE>", text)
    text, age_values = PATIENT_AGE_VALUE.subn(r"\g<lead><REDACTED_AGE>", text)
    report.redacted_terms += dates + identifiers + ages + age_values
    return text


def sanitize_json_line(
    line: str, *, config: SanitizerConfig, report: FileReport
) -> str | None:
    """Sanitize one JSON event line structurally; None if it is not an event.

    A line that starts like JSON but does not parse is withheld whole: its tool
    output cannot be separated from agent text, and line regexes do not reach
    values inside escaped strings.
    """
    stripped = line.strip()
    if not stripped.startswith(("{", "[")):
        return None
    newline = "\n" if line.endswith("\n") else ""
    try:
        event = json.loads(stripped)
    except json.JSONDecodeError:
        if stripped.startswith("["):  # a bracketed log line, not an event
            return None
        report.withheld_unparseable += 1
        event_type = re.match(r'\{\s*"type"\s*:\s*"([A-Za-z_.]+)"', stripped)
        placeholder = {
            "type": "redacted_unparseable_event",
            "original_type": event_type.group(1) if event_type else None,
            "chars": len(stripped),
            "hmac_prefix": keyed_digest(stripped, config.salt),
        }
        return json.dumps(placeholder) + newline
    event = redact_tool_outputs(event, report, config.salt)
    event = sanitize_event_strings(event, config=config, report=report)
    return json.dumps(event, ensure_ascii=False) + newline


def looks_like_event_fragment(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and (
        '":' in stripped or '\\"' in stripped or stripped[-1] in "}]"
    )


def sanitize_text_payload(
    text: str,
    *,
    config: SanitizerConfig,
    report: FileReport,
    event_stream: bool = False,
) -> str:
    """Sanitize trace-like text: JSON event lines structurally, others as text.

    With `event_stream`, the text is a tail of a JSON event stream, so a
    non-JSON line that looks like part of an event (a truncated first line) is
    withheld as well.
    """
    out = []
    # JSON Lines are delimited by "\n" only; str.splitlines would also break
    # events at U+2028 and similar characters inside strings.
    for line in re.split(r"(?<=\n)", text):
        if not line:
            continue
        structured = sanitize_json_line(line, config=config, report=report)
        if structured is not None:
            out.append(structured)
            continue
        if event_stream and looks_like_event_fragment(line):
            report.withheld_unparseable += 1
            newline = "\n" if line.endswith("\n") else ""
            out.append(
                f'<REDACTED_EVENT_FRAGMENT chars="{len(line.strip())}" '
                f'hmac_prefix="{keyed_digest(line.strip(), config.salt)}">{newline}'
            )
            continue
        out.append(scrub_record_values(line, config=config, report=report))
    return redact_trace_data_blocks("".join(out), config=config, report=report)


def sanitize_text_file(
    source: Path,
    dest: Path,
    *,
    rel_path: Path,
    config: SanitizerConfig,
) -> FileReport:
    report = base_file_report(
        source,
        rel_path,
        "text_sanitized",
        collect_input_hash=config.collect_input_hashes,
    )
    text = source.read_text(encoding="utf-8", errors="replace")
    sanitized = sanitize_text_payload(text, config=config, report=report)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(sanitized, encoding="utf-8")
    finish_file_report(dest, report)
    return report


def copy_file(source: Path, dest: Path, *, rel_path: Path) -> FileReport:
    report = base_file_report(source, rel_path, "copied", collect_input_hash=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    finish_file_report(dest, report)
    return report


def skip_file(source: Path, *, rel_path: Path, reason: str) -> FileReport:
    report = base_file_report(source, rel_path, "skipped")
    report.warnings.append(reason)
    return report


def base_file_report(
    source: Path,
    rel_path: Path,
    action: str,
    *,
    collect_input_hash: bool = True,
) -> FileReport:
    return FileReport(
        path=rel_path.as_posix(),
        action=action,
        input_size_bytes=source.stat().st_size,
        input_sha256=sha256_file(source) if collect_input_hash else "",
    )


def finish_file_report(dest: Path, report: FileReport) -> None:
    report.output_size_bytes = dest.stat().st_size
    report.output_sha256 = sha256_file(dest)
    report.transformed_columns = sorted(set(report.transformed_columns))


def sanitize_path(
    source: Path,
    dest: Path,
    *,
    rel_path: Path,
    config: SanitizerConfig,
) -> FileReport:
    if source.name in SKIP_NAMES:
        return skip_file(source, rel_path=rel_path, reason="operating-system metadata")
    if source.suffix in SKIP_SUFFIXES:
        return skip_file(
            source, rel_path=rel_path, reason="binary/temp/private artifact"
        )
    if source.suffix in CSV_SUFFIXES:
        return sanitize_csv_file(source, dest, rel_path=rel_path, config=config)
    if source.suffix == ".json":
        return sanitize_json_file(source, dest, rel_path=rel_path, config=config)
    if source.suffix in TEXT_SUFFIXES:
        return sanitize_text_file(source, dest, rel_path=rel_path, config=config)
    if config.copy_binary:
        return copy_file(source, dest, rel_path=rel_path)
    return skip_file(source, rel_path=rel_path, reason="unrecognized suffix")


def sanitized_payload_for(
    source: Path,
    *,
    rel_path: Path,
    config: SanitizerConfig,
) -> tuple[bytes, FileReport]:
    """Sanitize one file and return bytes plus the file report.

    The release packager uses this to stream sanitized files into a tarball
    without first materializing a full sanitized artifact tree.
    """
    with tempfile.TemporaryDirectory(prefix="m4-sanitize-") as tmp:
        dest = Path(tmp) / rel_path.name
        report = sanitize_path(source, dest, rel_path=rel_path, config=config)
        if report.action == "skipped":
            return b"", report
        return dest.read_bytes(), report


def iter_files(source: Path) -> list[Path]:
    if source.is_file():
        return [source]
    return sorted(path for path in source.rglob("*") if path.is_file())


def sanitize_tree(
    source: Path,
    output: Path,
    *,
    config: SanitizerConfig,
    dry_run: bool = False,
    include_private_report_details: bool = False,
) -> SanitizationReport:
    report = SanitizationReport(source=str(source), output=str(output))
    report.private_patterns_loaded = bool(
        config.private_patterns.literals or config.private_patterns.regexes
    )
    report.private_literal_patterns = len(config.private_patterns.literals)
    report.private_regex_patterns = len(config.private_patterns.regexes)

    source = source.resolve()
    output = output.resolve()
    if output.exists() and not dry_run:
        raise SystemExit(f"Output path already exists: {output}")
    if not dry_run:
        output.mkdir(parents=True, exist_ok=False)

    for path in iter_files(source):
        rel_path = path.name if source.is_file() else path.relative_to(source)
        rel = Path(rel_path)
        dest = output / rel
        if dry_run:
            file_report = base_file_report(
                path,
                rel,
                "would_sanitize",
                collect_input_hash=config.collect_input_hashes,
            )
        else:
            file_report = sanitize_path(path, dest, rel_path=rel, config=config)
        if file_report.action == "skipped":
            report.skipped_files += 1
        report.files.append(file_report)

    if not dry_run:
        report_path = output / "SANITIZATION_REPORT.json"
        report_path.write_text(
            json.dumps(
                report.to_json(include_private_details=include_private_report_details),
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
    return report


def print_summary(report: SanitizationReport) -> None:
    data = report.to_json()
    summary = data["summary"]
    print(f"Files: {summary['files']}")
    print(f"Actions: {summary['actions']}")
    print(f"CSV rows processed: {summary['csv_rows_processed']}")
    print(f"Redacted trace/data blocks: {summary['redacted_trace_blocks']}")
    print(f"Redacted private terms: {summary['redacted_private_terms']}")
    print(f"Remaining @ signs: {summary['remaining_at_signs']}")
    print(f"Skipped files: {summary['skipped_files']}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Source artifact file or directory.")
    parser.add_argument("output", type=Path, help="Output sanitized directory.")
    parser.add_argument(
        "--private-patterns",
        type=Path,
        help=(
            "Gitignored literal/regex redaction file. Defaults to "
            "M4BENCH_PRIVATE_REDACTIONS or benchmark/release/v1/.private_redactions."
        ),
    )
    parser.add_argument(
        "--salt-file",
        type=Path,
        help=(
            "Gitignored HMAC salt file. Defaults to M4BENCH_SANITIZE_SALT_FILE or "
            "benchmark/release/v1/.private_sanitize_salt."
        ),
    )
    parser.add_argument(
        "--salt",
        help="Private HMAC salt value. Prefer --salt-file or M4BENCH_SANITIZE_SALT.",
    )
    parser.add_argument(
        "--allow-insecure-salt",
        action="store_true",
        help="Use a public test salt if no private salt is configured. Do not use for release.",
    )
    parser.add_argument(
        "--csv-mode",
        choices=["scores-only", "pseudonymized-full"],
        default="scores-only",
        help=(
            "scores-only keeps row_id plus score/result columns. "
            "pseudonymized-full keeps all CSV columns with IDs/times transformed."
        ),
    )
    parser.add_argument(
        "--include-row-key-hash",
        action="store_true",
        help=(
            "In scores-only mode, include a private-salt HMAC over original row keys. "
            "This improves private auditability but is riskier than row_id alone."
        ),
    )
    parser.add_argument(
        "--time-mode",
        choices=["offset-hours", "date", "keep"],
        default="offset-hours",
        help="How to sanitize timestamp-like columns in pseudonymized-full CSV mode.",
    )
    parser.add_argument(
        "--copy-binary",
        action="store_true",
        help="Copy unrecognized binary files instead of skipping them.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inventory selected files without writing a sanitized directory.",
    )
    parser.add_argument(
        "--include-private-report-details",
        action="store_true",
        help="Include absolute source/output paths and raw input hashes in the report. Do not publish this report.",
    )
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    config = SanitizerConfig(
        salt=load_salt(args),
        private_patterns=load_private_patterns(args.private_patterns),
        csv_mode=args.csv_mode,
        time_mode=args.time_mode,
        copy_binary=args.copy_binary,
        include_row_key_hash=args.include_row_key_hash,
        collect_input_hashes=args.include_private_report_details,
    )
    report = sanitize_tree(
        args.source,
        args.output,
        config=config,
        dry_run=args.dry_run,
        include_private_report_details=args.include_private_report_details,
    )
    print_summary(report)
    if not args.dry_run:
        print(f"Wrote sanitized artifacts to {args.output}")
        print(f"Wrote {args.output / 'SANITIZATION_REPORT.json'}")


if __name__ == "__main__":
    main()
