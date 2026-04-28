"""Preflight checks for paper-quality M4Bench campaigns.

Run before launching expensive model runs:

    python benchmark/preflight.py --results-root benchmark/results/paper-YYYYMMDD

Use `--ground-truth-self-check` when you also want the slower evaluator
round-trip over every ground-truth file.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from evaluate import evaluate, resolve_ground_truth
from lib.db import SOURCE_DBS, _db_prefix, _task_key, list_task_dirs, load_task_config

BENCHMARK_ROOT = Path(__file__).parent
AGENT_DB_DIR = BENCHMARK_ROOT / "agent_db"
GROUND_TRUTH_DIR = BENCHMARK_ROOT / "ground_truth"

BENCHMARK_NOTE = (
    "target concept tables listed in the task configuration are removed or "
    "unavailable in the agent database"
)

TASK_REQUIRED_DROPS = {
    "mimic-creatinine-baseline-raw": {
        "mimiciv_derived.age",
        "mimiciv_derived.apsiii",
        "mimiciv_derived.chemistry",
        "mimiciv_derived.creatinine_baseline",
        "mimiciv_derived.first_day_lab",
        "mimiciv_derived.kdigo_creatinine",
        "mimiciv_derived.kdigo_stages",
        "mimiciv_derived.meld",
        "mimiciv_derived.oasis",
        "mimiciv_derived.sofa",
    },
    "mimic-suspicion-infection": {
        "mimiciv_derived.sepsis3",
        "mimiciv_derived.suspicion_of_infection",
    },
    "mimic-suspicion-infection-raw": {
        "mimiciv_derived.antibiotic",
        "mimiciv_derived.sepsis3",
        "mimiciv_derived.suspicion_of_infection",
    },
    "mimic-urine-output-rate": {
        "mimiciv_derived.kdigo_stages",
        "mimiciv_derived.kdigo_uo",
        "mimiciv_derived.urine_output_rate",
    },
    "mimic-urine-output-rate-raw": {
        "mimiciv_derived.first_day_urine_output",
        "mimiciv_derived.first_day_weight",
        "mimiciv_derived.icustay_detail",
        "mimiciv_derived.icustay_hourly",
        "mimiciv_derived.icustay_times",
        "mimiciv_derived.kdigo_creatinine",
        "mimiciv_derived.kdigo_stages",
        "mimiciv_derived.kdigo_uo",
        "mimiciv_derived.urine_output",
        "mimiciv_derived.urine_output_rate",
        "mimiciv_derived.weight_durations",
    },
    "mimic-kdigo-48h-raw": {
        "mimiciv_derived.apsiii",
        "mimiciv_derived.charlson",
        "mimiciv_derived.chemistry",
        "mimiciv_derived.creatinine_baseline",
        "mimiciv_derived.crrt",
        "mimiciv_derived.first_day_lab",
        "mimiciv_derived.first_day_rrt",
        "mimiciv_derived.first_day_sofa",
        "mimiciv_derived.first_day_urine_output",
        "mimiciv_derived.first_day_weight",
        "mimiciv_derived.icustay_detail",
        "mimiciv_derived.icustay_hourly",
        "mimiciv_derived.icustay_times",
        "mimiciv_derived.kdigo_creatinine",
        "mimiciv_derived.kdigo_stages",
        "mimiciv_derived.kdigo_uo",
        "mimiciv_derived.lods",
        "mimiciv_derived.meld",
        "mimiciv_derived.oasis",
        "mimiciv_derived.rrt",
        "mimiciv_derived.sapsii",
        "mimiciv_derived.sepsis3",
        "mimiciv_derived.sofa",
        "mimiciv_derived.urine_output",
        "mimiciv_derived.urine_output_rate",
        "mimiciv_derived.weight_durations",
    },
    "mimic-meld-24h-raw": {
        "mimiciv_derived.apsiii",
        "mimiciv_derived.bg",
        "mimiciv_derived.chemistry",
        "mimiciv_derived.coagulation",
        "mimiciv_derived.creatinine_baseline",
        "mimiciv_derived.crrt",
        "mimiciv_derived.enzyme",
        "mimiciv_derived.first_day_bg",
        "mimiciv_derived.first_day_bg_art",
        "mimiciv_derived.first_day_lab",
        "mimiciv_derived.first_day_rrt",
        "mimiciv_derived.first_day_sofa",
        "mimiciv_derived.kdigo_creatinine",
        "mimiciv_derived.kdigo_stages",
        "mimiciv_derived.meld",
        "mimiciv_derived.rrt",
        "mimiciv_derived.sapsii",
        "mimiciv_derived.sofa",
    },
    "mimic-vasopressor-equivalents-raw": {
        "mimiciv_derived.dobutamine",
        "mimiciv_derived.dopamine",
        "mimiciv_derived.epinephrine",
        "mimiciv_derived.first_day_sofa",
        "mimiciv_derived.milrinone",
        "mimiciv_derived.norepinephrine",
        "mimiciv_derived.norepinephrine_equivalent_dose",
        "mimiciv_derived.phenylephrine",
        "mimiciv_derived.sofa",
        "mimiciv_derived.vasoactive_agent",
        "mimiciv_derived.vasopressin",
        "mimiciv_derived.weight_durations",
    },
}

TASK_FORBIDDEN_DERIVED_COLUMN_PATTERNS = {
    "mimic-creatinine-baseline-raw": re.compile(
        r"creat|scr|mdrd|\bage\b",
        re.IGNORECASE,
    ),
    "mimic-suspicion-infection": re.compile(
        r"sepsis3|suspicion_of_infection|suspected_infection|"
        r"positive_culture|culture_time",
        re.IGNORECASE,
    ),
    "mimic-suspicion-infection-raw": re.compile(
        r"antibiotic|sepsis3|suspicion_of_infection|suspected_infection|"
        r"positive_culture|culture_time",
        re.IGNORECASE,
    ),
    "mimic-vasopressor-equivalents-raw": re.compile(
        r"vaso|norepi|epinephrine|dopamine|phenylephrine|vasopressin|"
        r"dobutamine|milrinone",
        re.IGNORECASE,
    ),
    "mimic-kdigo-48h-raw": re.compile(
        r"aki|creat|crrt|dialysis|kdigo|renal|rrt|urine|uo|weight",
        re.IGNORECASE,
    ),
    "mimic-meld-24h-raw": re.compile(
        r"meld|bilirubin|creat|crrt|dialysis|inr|rrt|sodium",
        re.IGNORECASE,
    ),
}


@dataclass
class CheckResult:
    name: str
    ok: bool
    details: list[str]


def _ok(name: str, *details: str) -> CheckResult:
    return CheckResult(name=name, ok=True, details=list(details))


def _fail(name: str, details: list[str]) -> CheckResult:
    return CheckResult(name=name, ok=False, details=details)


def _task_name(task_dir: Path) -> str:
    return load_task_config(task_dir)["metadata"]["name"]


def _agent_db_path(task_name: str) -> Path:
    return AGENT_DB_DIR / f"{_db_prefix(task_name)}_{_task_key(task_name)}.duckdb"


def check_instruction_sparsity() -> CheckResult:
    """Instructions should not contain dataset-specific lookup answers."""
    problems: list[str] = []
    patterns = [
        (re.compile(r"\bmimiciv_", re.IGNORECASE), "MIMIC schema/table prefix"),
        (re.compile(r"\bitemid\b", re.IGNORECASE), "itemid"),
        (re.compile(r"```sql", re.IGNORECASE), "SQL code block"),
        (re.compile(r"\bSELECT\b", re.IGNORECASE), "SELECT statement"),
    ]
    for task_dir in list_task_dirs():
        instruction_path = task_dir / "instruction.md"
        text = instruction_path.read_text()
        for pattern, label in patterns:
            if pattern.search(text):
                problems.append(f"{_task_name(task_dir)}: instruction contains {label}")

    if problems:
        return _fail("instruction sparsity", problems)
    return _ok(
        "instruction sparsity", "instructions avoid table names, item IDs, and SQL"
    )


def check_taskcards_not_agent_adjacent() -> CheckResult:
    """Solution-level taskcards must not live under benchmark/tasks."""
    taskcards = sorted(BENCHMARK_ROOT.glob("tasks/*/TASKCARD.md"))
    if taskcards:
        return _fail(
            "taskcard release safety",
            [
                f"{path.relative_to(BENCHMARK_ROOT)} should live under internal_taskcards/"
                for path in taskcards
            ],
        )
    return _ok(
        "taskcard release safety",
        "solution-level taskcards are outside the task tree scanned/mounted for runs",
    )


def check_raw_mode_contract() -> CheckResult:
    """Raw task wording must match the actual task-specific drop strategy."""
    problems: list[str] = []
    forbidden = [
        "Only base tables are available",
        "there are no pre-computed derived tables",
        "forcing the agent to work from base tables",
    ]
    for task_dir in list_task_dirs():
        config = load_task_config(task_dir)
        task_name = config["metadata"]["name"]
        required_drops = TASK_REQUIRED_DROPS.get(task_name, set())
        configured_drops = set(config.get("database", {}).get("drop_tables", []))
        missing_drops = sorted(required_drops - configured_drops)
        if missing_drops:
            problems.append(
                f"{task_name}: task is missing required shortcut drops: "
                + ", ".join(missing_drops)
            )

        if config["metadata"].get("mode") != "raw":
            continue
        instruction_path = task_dir / "instruction.md"
        text = instruction_path.read_text()
        for needle in forbidden:
            if needle in text:
                problems.append(
                    f"{_task_name(task_dir)}: raw instruction still says `{needle}`"
                )

    readme_text = (BENCHMARK_ROOT / "README.md").read_text()
    if "forcing the agent to work from base tables" in readme_text:
        problems.append("README raw-mode definition still claims base-table-only mode")

    if problems:
        return _fail("raw-mode contract", problems)
    return _ok(
        "raw-mode contract",
        "raw MIMIC tasks remove the derived shortcut schema at DB setup time",
    )


def check_skill_snapshots() -> CheckResult:
    """Task-local skill snapshots should not expose target table answers."""
    problems: list[str] = []
    forbidden_text = [
        "## Pre-computed Table",
        "## Pre-computed Tables",
        "scripts/",
        "BigQuery users already have this table",
        "full SQL query",
    ]
    forbidden_query = re.compile(
        r"\b(FROM|JOIN)\s+mimiciv_derived\.[A-Za-z0-9_]+", re.IGNORECASE
    )

    for task_dir in list_task_dirs():
        config = load_task_config(task_dir)
        task_name = config["metadata"]["name"]
        drop_tables = set(config.get("database", {}).get("drop_tables", []))
        skills_dir = task_dir / "skills"
        if not skills_dir.exists():
            continue

        for extra_file in skills_dir.rglob("*"):
            if extra_file.is_file() and extra_file.name != "SKILL.md":
                problems.append(f"{task_name}: unexpected skill artifact {extra_file}")

        for skill_path in sorted(skills_dir.glob("*/SKILL.md")):
            text = skill_path.read_text()
            rel = skill_path.relative_to(BENCHMARK_ROOT)
            if not text.startswith("---"):
                problems.append(f"{task_name}: missing frontmatter in {rel}")
            else:
                frontmatter = text.split("---", 2)[1]
                keys = {
                    line.split(":", 1)[0].strip()
                    for line in frontmatter.splitlines()
                    if ":" in line
                }
                for key in ("name", "description", "tier", "category"):
                    if key not in keys:
                        problems.append(
                            f"{task_name}: missing `{key}` frontmatter in {rel}"
                        )
            normalized_text = " ".join(text.split())
            if BENCHMARK_NOTE not in normalized_text:
                problems.append(f"{task_name}: missing M4Bench-use note in {rel}")
            for needle in forbidden_text:
                if needle in text:
                    problems.append(f"{task_name}: forbidden '{needle}' in {rel}")
            if forbidden_query.search(text):
                problems.append(
                    f"{task_name}: derived-table SQL query remains in {rel}"
                )
            for table in sorted(drop_tables):
                if table in text:
                    problems.append(
                        f"{task_name}: dropped table `{table}` appears in {rel}"
                    )

    if problems:
        return _fail("skill snapshot leakage", problems)
    return _ok(
        "skill snapshot leakage",
        "skills contain no dropped table names, target queries, or script artifacts",
    )


def check_isolation_guardrails() -> CheckResult:
    """Source-level check that publishable Docker isolation covers known leaks."""
    problems: list[str] = []

    from run import FILESYSTEM_CANARY_CHECKS

    canary_commands = "\n".join(cmd for _name, cmd in FILESYSTEM_CANARY_CHECKS)
    required_canary_paths = [
        "/benchmark/ground_truth",
        "/benchmark/tasks",
        "/benchmark/agent_db",
        "/benchmark/results",
        "/tmp/clinskillsbench/_db_cache",
        "/host-auth",
        "/claude-auth",
        "/benchmark/lib/dictionary.json",
    ]
    for path in required_canary_paths:
        if path not in canary_commands:
            problems.append(f"filesystem canary does not cover {path}")

    bench_text = (BENCHMARK_ROOT / "bench.sh").read_text()
    forbidden_mounts = [
        "$HOME/.codex:$AUTH_ROOT/.codex:ro",
        "$HOME/.gemini:$AUTH_ROOT/.gemini:ro",
        "$HOME/.pi:$AUTH_ROOT/.pi:ro",
        '-v "$SCRIPT_DIR":/benchmark',
    ]
    for needle in forbidden_mounts:
        if needle in bench_text:
            problems.append(f"bench.sh still mounts full auth directory: {needle}")

    required_bench_fragments = [
        "AUTH_STAGING_DIR=",
        'stage_auth_file ".codex/auth.json"',
        'stage_auth_file ".gemini/oauth_creds.json"',
        'stage_auth_file ".pi/agent/models.json"',
        'chmod -R go-rwx "$AUTH_STAGING_DIR"',
        "M4BENCH_AGENT_CONTAINER=1",
        "M4BENCH_AGENT_CONTAINER_MOUNTS",
        "M4BENCH_CLAUDE_AUTH_ROOT",
        "Running preflight checks",
    ]
    for fragment in required_bench_fragments:
        if fragment not in bench_text:
            problems.append(f"bench.sh missing isolation guard: {fragment}")

    login_text = (BENCHMARK_ROOT / "claude_login_container.sh").read_text()
    if "chmod -R go-rwx /claude-auth" not in login_text:
        problems.append("claude_login_container.sh does not lock Claude auth volume")
    if "M4BENCH_CLAUDE_AUTH_MODE" in bench_text + login_text:
        problems.append("Claude auth mode switch should not be used")

    run_text = (BENCHMARK_ROOT / "run.py").read_text()
    network_text = (BENCHMARK_ROOT / "network_lock.sh").read_text()
    if "DB_CACHE.chmod(0o700)" not in run_text:
        problems.append("run.py does not make the cross-task DB cache private")
    if "cached_db.chmod(0o600)" not in run_text:
        problems.append("run.py does not make cached DB files private")
    if (
        "mount benchmark/tasks, benchmark/ground_truth, benchmark/results"
        not in run_text
    ):
        problems.append("run.py does not document sensitive paths as unmounted")
    if "SECRET_ENV_KEYS" not in run_text or "M4BENCH_AGENT_ENV_FILE" not in run_text:
        problems.append("run.py still passes API keys through docker metadata")
    if "egress.jsonl" not in run_text or "disallowed_egress" not in run_text:
        problems.append("run.py does not lint structured egress proxy logs")
    if "CONNECT" not in network_text or "M4BENCH_ALLOWED_LLM_HOSTS" not in network_text:
        problems.append("network_lock.sh does not enforce hostname-level proxy egress")
    forbidden_network_hosts = [
        "chatgpt.com",
        "auth.openai.com",
        "oauth2.googleapis.com",
        "accounts.google.com",
        "statsig.anthropic.com",
        "sentry.io",
    ]
    for host in forbidden_network_hosts:
        if host in network_text:
            problems.append(f"network allowlist still includes non-API host: {host}")

    if problems:
        return _fail("isolation guardrails", problems)
    return _ok(
        "isolation guardrails",
        "canaries cover real sensitive paths; agent container omits benchmark secrets",
    )


def check_agent_databases() -> CheckResult:
    """Agent DBs must exist and have task target tables dropped."""
    try:
        import duckdb
    except ImportError:
        return _fail("agent databases", ["duckdb is not installed"])

    problems: list[str] = []
    checked_tables = 0
    for task_dir in list_task_dirs():
        config = load_task_config(task_dir)
        task_name = config["metadata"]["name"]
        db_path = _agent_db_path(task_name)
        if not db_path.exists():
            problems.append(f"{task_name}: missing agent DB {db_path}")
            continue

        drop_tables = config.get("database", {}).get("drop_tables", [])
        if not drop_tables:
            continue

        con = duckdb.connect(str(db_path), read_only=True)
        try:
            if (
                config.get("metadata", {}).get("mode") == "raw"
                and config.get("database", {}).get("source", "mimic-iv") == "mimic-iv"
            ):
                remaining_derived = con.execute(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.tables
                    WHERE table_schema = 'mimiciv_derived'
                    """
                ).fetchone()[0]
                if remaining_derived:
                    problems.append(
                        f"{task_name}: raw DB still exposes "
                        f"{remaining_derived} mimiciv_derived relations"
                    )

            for table in drop_tables:
                schema, table_name = table.split(".", 1)
                present = con.execute(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.tables
                    WHERE table_schema = ? AND table_name = ?
                    """,
                    [schema, table_name],
                ).fetchone()[0]
                checked_tables += 1
                if present:
                    problems.append(
                        f"{task_name}: dropped table still present: {table}"
                    )

            pattern = TASK_FORBIDDEN_DERIVED_COLUMN_PATTERNS.get(task_name)
            if pattern is not None:
                rows = con.execute(
                    """
                    SELECT table_schema, table_name, column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'mimiciv_derived'
                    ORDER BY table_schema, table_name, ordinal_position
                    """
                ).fetchall()
                leaks = [
                    f"{schema}.{table_name}.{column_name}"
                    for schema, table_name, column_name in rows
                    if pattern.search(f"{table_name} {column_name}")
                ]
                if leaks:
                    problems.append(
                        f"{task_name}: derived shortcut columns "
                        f"still present: {', '.join(leaks)}"
                    )
        finally:
            con.close()

    if problems:
        return _fail("agent databases", problems)
    return _ok(
        "agent databases",
        f"all agent DBs present; {checked_tables} configured drop tables absent",
    )


def _duckdb_relation_exists(con, fqn: str) -> bool:
    schema, table_name = fqn.split(".", 1)
    return bool(
        con.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = ? AND table_name = ?
            """,
            [schema, table_name],
        ).fetchone()[0]
    )


def _external_view_paths(db_path: Path) -> list[Path]:
    """Return external m4_data paths referenced by read_parquet() views."""
    import duckdb

    paths: list[Path] = []
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT sql
            FROM duckdb_views()
            WHERE NOT internal
              AND lower(sql) LIKE '%read_parquet(%m4_data/%'
            """
        ).fetchall()
    finally:
        con.close()

    for (sql,) in rows:
        for match in re.finditer(r"read_parquet\('([^']+)'\)", sql, re.IGNORECASE):
            paths.append(Path(match.group(1)))
    return paths


def check_external_view_sources() -> CheckResult:
    """External Parquet-backed views must point at local m4_data files."""
    try:
        import duckdb  # noqa: F401
    except ImportError:
        return _fail("external view sources", ["duckdb is not installed"])

    problems: list[str] = []
    checked_dbs = 0
    checked_paths: set[Path] = set()

    for db_path in sorted(AGENT_DB_DIR.glob("*.duckdb")):
        checked_dbs += 1
        for path in _external_view_paths(db_path):
            if path in checked_paths:
                continue
            checked_paths.add(path)
            if glob.has_magic(str(path)):
                if not glob.glob(str(path)):
                    problems.append(f"{db_path.name}: no files match {path}")
            elif not path.exists():
                problems.append(f"{db_path.name}: missing external view source {path}")

    if problems:
        return _fail("external view sources", problems[:20])
    if not checked_paths:
        return _ok(
            "external view sources",
            f"{checked_dbs} agent DBs have no external Parquet-backed views",
        )
    return _ok(
        "external view sources",
        (
            f"{len(checked_paths)} external Parquet sources exist; "
            "bench.sh mounts only required Parquet sources into Docker"
        ),
    )


def _sha256_file(path: Path, cache: dict[Path, str] | None = None) -> str:
    resolved = path.resolve()
    if cache is not None and resolved in cache:
        return cache[resolved]
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    value = digest.hexdigest()
    if cache is not None:
        cache[resolved] = value
    return value


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _manifest_path(csv_path: Path) -> Path:
    return csv_path.with_suffix("").with_suffix(".manifest.json")


def _validate_ground_truth_manifest(
    *,
    task_name: str,
    task_key: str,
    csv_path: Path,
    config: dict,
    file_hashes: dict[Path, str],
) -> list[str]:
    problems: list[str] = []
    manifest_path = _manifest_path(csv_path)
    if not manifest_path.exists():
        return [f"{task_name}: missing ground-truth manifest {manifest_path}"]

    try:
        manifest = json.loads(manifest_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return [f"{task_name}: unreadable ground-truth manifest {manifest_path}: {exc}"]

    csv_sha = _sha256_file(csv_path, file_hashes)
    if manifest.get("csv_sha256") != csv_sha:
        problems.append(f"{task_name}: manifest CSV hash does not match {csv_path}")

    source = manifest.get("source")
    if source == "alias":
        alias = manifest.get("alias_target")
        alias_path = GROUND_TRUTH_DIR / f"{alias}.csv.gz"
        if not alias or not alias_path.exists():
            problems.append(f"{task_name}: alias target CSV missing for {alias}")
            return problems
        if manifest.get("alias_csv_sha256") != _sha256_file(alias_path, file_hashes):
            problems.append(f"{task_name}: alias target hash is stale for {alias}")
        alias_manifest_path = _manifest_path(alias_path)
        if not alias_manifest_path.exists():
            problems.append(f"{task_name}: alias target manifest missing for {alias}")
        else:
            try:
                alias_manifest = json.loads(alias_manifest_path.read_text())
            except (json.JSONDecodeError, OSError) as exc:
                problems.append(
                    f"{task_name}: unreadable alias target manifest for {alias}: {exc}"
                )
                return problems
            if manifest.get("alias_manifest", {}).get("csv_sha256") != _sha256_file(
                alias_path, file_hashes
            ):
                problems.append(
                    f"{task_name}: embedded alias manifest is stale for {alias}"
                )
            sql_rel = alias_manifest.get("sql_path")
            sql_path = (
                BENCHMARK_ROOT / sql_rel
                if sql_rel
                else GROUND_TRUTH_DIR / f"{alias}.sql"
            )
            if not sql_path.exists():
                problems.append(f"{task_name}: alias SQL path missing: {sql_path}")
            elif alias_manifest.get("sql_sha256") != _sha256_text(sql_path.read_text()):
                problems.append(f"{task_name}: alias SQL hash is stale for {alias}")
            db_source = config.get("database", {}).get("source", "mimic-iv")
            db_path = SOURCE_DBS.get(db_source, SOURCE_DBS["mimic-iv"])
            if not db_path.exists():
                problems.append(
                    f"{task_name}: source DB missing for alias manifest validation: "
                    f"{db_path}"
                )
            elif alias_manifest.get("db_sha256") != _sha256_file(db_path, file_hashes):
                problems.append(
                    f"{task_name}: source DB hash changed since alias generation"
                )
        return problems

    if source != "sql":
        problems.append(f"{task_name}: unknown ground-truth manifest source {source!r}")
        return problems

    sql_rel = manifest.get("sql_path")
    sql_path = (
        BENCHMARK_ROOT / sql_rel if sql_rel else GROUND_TRUTH_DIR / f"{task_key}.sql"
    )
    if not sql_path.exists():
        problems.append(f"{task_name}: manifest SQL path missing: {sql_path}")
    elif manifest.get("sql_sha256") != _sha256_text(sql_path.read_text()):
        problems.append(f"{task_name}: ground-truth SQL hash is stale: {sql_path}")

    db_source = config.get("database", {}).get("source", "mimic-iv")
    db_path = SOURCE_DBS.get(db_source, SOURCE_DBS["mimic-iv"])
    if not db_path.exists():
        problems.append(
            f"{task_name}: source DB missing for manifest validation: {db_path}"
        )
    elif manifest.get("db_sha256") != _sha256_file(db_path, file_hashes):
        problems.append(
            f"{task_name}: source DB hash changed since ground truth generation"
        )

    if not manifest.get("duckdb_version"):
        problems.append(f"{task_name}: manifest missing DuckDB version")
    if not manifest.get("sorted_by"):
        problems.append(f"{task_name}: manifest missing deterministic sort columns")
    return problems


def check_ground_truth(self_check: bool = False) -> CheckResult:
    """Ground-truth files must exist; optionally verify GT evaluates to 1.0."""
    problems: list[str] = []
    checked = 0
    file_hashes: dict[Path, str] = {}
    for task_dir in list_task_dirs():
        config = load_task_config(task_dir)
        task_name = _task_name(task_dir)
        task_key = _task_key(task_name)
        try:
            gt_path = resolve_ground_truth(task_name)
        except FileNotFoundError as exc:
            problems.append(str(exc))
            continue
        problems.extend(
            _validate_ground_truth_manifest(
                task_name=task_name,
                task_key=task_key,
                csv_path=Path(gt_path),
                config=config,
                file_hashes=file_hashes,
            )
        )

        if self_check:
            results = evaluate(task_name, str(gt_path))
            reward = results.get("reward")
            if reward != 1.0:
                problems.append(f"{task_name}: ground truth self-check reward={reward}")
        checked += 1

    if problems:
        return _fail("ground truth", problems)
    suffix = "and self-evaluate to 1.0" if self_check else "exist"
    return _ok("ground truth", f"{checked} ground-truth files {suffix}")


def check_contamination_ready() -> CheckResult:
    """Tier 5 should have complete transformed DBs, GT SQL, and no targets."""
    try:
        import duckdb
    except ImportError:
        return _fail("contamination readiness", ["duckdb is not installed"])

    try:
        from lib.transform import load_dictionary

        dictionary = load_dictionary()
    except Exception as exc:
        return _fail("contamination readiness", [f"dictionary unavailable: {exc}"])

    gt_key_by_task_key: dict[str, str] = {}
    config_by_task_key: dict[str, dict] = {}
    for task_dir in list_task_dirs():
        config = load_task_config(task_dir)
        if config.get("database", {}).get("source", "mimic-iv") != "mimic-iv":
            continue
        task_name = config["metadata"]["name"]
        task_key = _task_key(task_name)
        config_by_task_key[task_key] = config
        gt_key_by_task_key[task_key] = config.get("ground_truth", {}).get(
            "alias", task_key
        )

    expected = sorted(config_by_task_key)

    problems: list[str] = []
    checked_tables = 0
    if not expected:
        problems.append("no MIMIC-IV tasks found for contamination readiness")
    for schema_type in ("obfuscated", "restructured"):
        present = {
            path.name.removeprefix(f"{schema_type}_").removesuffix(".duckdb")
            for path in AGENT_DB_DIR.glob(f"{schema_type}_*.duckdb")
        }
        if not present:
            problems.append(f"no {schema_type} agent DBs found")

    for task_key in expected:
        config = config_by_task_key.get(task_key)
        if config is None:
            problems.append(f"{task_key}: no task.toml found for transformed DB")
            continue

        gt_key = gt_key_by_task_key.get(task_key, task_key)
        for schema_type in ("obfuscated", "restructured"):
            sql_path = BENCHMARK_ROOT / "ground_truth" / schema_type / f"{gt_key}.sql"
            if not sql_path.exists():
                problems.append(
                    f"{schema_type}: missing transformed ground-truth SQL for "
                    f"{task_key}"
                )

            db_path = AGENT_DB_DIR / f"{schema_type}_{task_key}.duckdb"
            if not db_path.exists():
                problems.append(f"{schema_type}: missing transformed DB for {task_key}")
                continue

            con = duckdb.connect(str(db_path), read_only=True)
            try:
                if config.get("metadata", {}).get("mode") == "raw":
                    derived_schema = dictionary["schemas"].get("mimiciv_derived")
                    remaining_derived = con.execute(
                        """
                        SELECT COUNT(*)
                        FROM information_schema.tables
                        WHERE table_schema = ?
                        """,
                        [derived_schema],
                    ).fetchone()[0]
                    if remaining_derived:
                        problems.append(
                            f"{schema_type}/{task_key}: raw DB still exposes "
                            f"{remaining_derived} transformed derived relations"
                        )

                for native_table in config.get("database", {}).get("drop_tables", []):
                    mapped_table = dictionary["tables"].get(native_table)
                    if mapped_table is None:
                        problems.append(
                            f"{schema_type}/{task_key}: dropped table not in "
                            f"dictionary: {native_table}"
                        )
                        continue
                    checked_tables += 1
                    if _duckdb_relation_exists(con, mapped_table):
                        problems.append(
                            f"{schema_type}/{task_key}: dropped table still present: "
                            f"{mapped_table} (was {native_table})"
                        )
            finally:
                con.close()

    if problems:
        return _fail("contamination readiness", problems)
    return _ok(
        "contamination readiness",
        (
            f"{len(expected)} obfuscated/restructured transformed task DBs ready for Tier 5; "
            f"{checked_tables} mapped drop-table checks passed"
        ),
    )


def check_results_root(
    results_root: str | None, *, allow_existing: bool = False
) -> CheckResult:
    if not results_root:
        return _ok(
            "results root",
            "no --results-root supplied; matrix.py will require one for Docker runs",
        )

    path = Path(results_root).expanduser().resolve()
    result_files = list(path.rglob("result.json")) if path.exists() else []
    if result_files:
        if allow_existing:
            return _ok(
                "results root",
                f"{path} contains {len(result_files)} existing result.json files",
            )
        return _fail(
            "results root",
            [f"{path} already contains {len(result_files)} result.json files"],
        )
    return _ok("results root", f"{path} is fresh for benchmark results")


def run_checks(
    results_root: str | None = None,
    check_dbs: bool = True,
    self_check_ground_truth: bool = False,
    allow_existing_results_root: bool = False,
) -> list[CheckResult]:
    # Keep check_dbs=False source-only so preflight can run in fresh checkouts
    # before expensive generated benchmark artifacts exist locally.
    checks = [
        check_instruction_sparsity(),
        check_taskcards_not_agent_adjacent(),
        check_raw_mode_contract(),
        check_skill_snapshots(),
        check_isolation_guardrails(),
        check_results_root(results_root, allow_existing=allow_existing_results_root),
    ]
    if check_dbs:
        checks.insert(2, check_agent_databases())
        checks.insert(3, check_external_view_sources())
        checks.insert(4, check_ground_truth(self_check=self_check_ground_truth))
        checks.insert(5, check_contamination_ready())
    return checks


def print_results(results: list[CheckResult]) -> None:
    for result in results:
        status = "OK" if result.ok else "FAIL"
        print(f"[{status}] {result.name}")
        for detail in result.details:
            print(f"  - {detail}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run M4Bench preflight checks")
    parser.add_argument(
        "--results-root",
        help="Fresh result directory planned for a paper campaign",
    )
    parser.add_argument(
        "--skip-db-check",
        action="store_true",
        help="Skip generated benchmark artifact checks (agent DBs, ground truth, contamination DBs)",
    )
    parser.add_argument(
        "--ground-truth-self-check",
        action="store_true",
        help="Evaluate each ground-truth file against itself (slower)",
    )
    parser.add_argument(
        "--allow-existing-results-root",
        action="store_true",
        help="Allow --results-root to contain previous runs",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    results = run_checks(
        results_root=args.results_root,
        check_dbs=not args.skip_db_check,
        self_check_ground_truth=args.ground_truth_self_check,
        allow_existing_results_root=args.allow_existing_results_root,
    )
    print_results(results)
    return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
