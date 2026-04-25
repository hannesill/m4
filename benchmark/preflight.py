"""Preflight checks for paper-quality M4Bench campaigns.

Run before launching expensive model runs:

    python benchmark/preflight.py --results-root benchmark/results/paper-YYYYMMDD

Use `--ground-truth-self-check` when you also want the slower evaluator
round-trip over every ground-truth file.
"""

from __future__ import annotations

import argparse
import glob
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from evaluate import evaluate, resolve_ground_truth
from lib.db import _db_prefix, _task_key, list_task_dirs, load_task_config

BENCHMARK_ROOT = Path(__file__).parent
AGENT_DB_DIR = BENCHMARK_ROOT / "agent_db"

BENCHMARK_NOTE = (
    "target concept tables listed in the task configuration are removed or "
    "unavailable in the agent database"
)

TASK_REQUIRED_DROPS = {
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
    },
}

TASK_FORBIDDEN_DERIVED_COLUMN_PATTERNS = {
    "mimic-vasopressor-equivalents-raw": re.compile(
        r"vaso|norepi|epinephrine|dopamine|phenylephrine|vasopressin|"
        r"dobutamine|milrinone",
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
        "raw tasks describe task-relevant derived-table removal, not base-only DBs",
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
                        f"{task_name}: derived vasopressor shortcut columns "
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


def check_ground_truth(self_check: bool = False) -> CheckResult:
    """Ground-truth files must exist; optionally verify GT evaluates to 1.0."""
    problems: list[str] = []
    checked = 0
    for task_dir in list_task_dirs():
        task_name = _task_name(task_dir)
        try:
            gt_path = resolve_ground_truth(task_name)
        except FileNotFoundError as exc:
            problems.append(str(exc))
            continue

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
    """Tier 5 should have paired obfuscated/restructured task DBs and GT SQL."""
    gt_key_by_task_key: dict[str, str] = {}
    for task_dir in list_task_dirs():
        config = load_task_config(task_dir)
        task_name = config["metadata"]["name"]
        task_key = _task_key(task_name)
        gt_key_by_task_key[task_key] = config.get("ground_truth", {}).get(
            "alias", task_key
        )

    obfuscated = {
        path.name.removeprefix("obfuscated_").removesuffix(".duckdb")
        for path in AGENT_DB_DIR.glob("obfuscated_*.duckdb")
    }
    restructured = {
        path.name.removeprefix("restructured_").removesuffix(".duckdb")
        for path in AGENT_DB_DIR.glob("restructured_*.duckdb")
    }
    paired = sorted(obfuscated & restructured)

    problems: list[str] = []
    if not paired:
        problems.append("no paired obfuscated/restructured agent DBs found")
    for task_key in paired:
        gt_key = gt_key_by_task_key.get(task_key, task_key)
        for schema in ("obfuscated", "restructured"):
            sql_path = BENCHMARK_ROOT / "ground_truth" / schema / f"{gt_key}.sql"
            if not sql_path.exists():
                problems.append(
                    f"{schema}: missing transformed ground-truth SQL for {task_key}"
                )

    if problems:
        return _fail("contamination readiness", problems)
    return _ok(
        "contamination readiness",
        f"{len(paired)} paired transformed task DBs ready for Tier 5",
    )


def check_results_root(results_root: str | None) -> CheckResult:
    if not results_root:
        return _ok(
            "results root",
            "no --results-root supplied; matrix.py will require one for Docker runs",
        )

    path = Path(results_root).expanduser().resolve()
    result_files = list(path.rglob("result.json")) if path.exists() else []
    if result_files:
        return _fail(
            "results root",
            [f"{path} already contains {len(result_files)} result.json files"],
        )
    return _ok("results root", f"{path} is fresh for benchmark results")


def run_checks(
    results_root: str | None = None,
    check_dbs: bool = True,
    self_check_ground_truth: bool = False,
) -> list[CheckResult]:
    # Keep check_dbs=False source-only so preflight can run in fresh checkouts
    # before expensive generated benchmark artifacts exist locally.
    checks = [
        check_instruction_sparsity(),
        check_raw_mode_contract(),
        check_skill_snapshots(),
        check_results_root(results_root),
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
    return parser


def main() -> int:
    args = build_parser().parse_args()
    results = run_checks(
        results_root=args.results_root,
        check_dbs=not args.skip_db_check,
        self_check_ground_truth=args.ground_truth_self_check,
    )
    print_results(results)
    return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
