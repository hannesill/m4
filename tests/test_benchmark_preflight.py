from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_preflight_instruction_sparsity_passes_current_tasks():
    preflight = _load_module(
        "benchmark_preflight_instruction", "benchmark/preflight.py"
    )

    result = preflight.check_instruction_sparsity()

    assert result.ok, result.details


def test_preflight_raw_mode_contract_matches_current_tasks():
    preflight = _load_module(
        "benchmark_preflight_raw_contract", "benchmark/preflight.py"
    )

    result = preflight.check_raw_mode_contract()

    assert result.ok, result.details


def test_urine_output_raw_drops_derived_shortcuts():
    preflight = _load_module(
        "benchmark_preflight_urine_raw_drops", "benchmark/preflight.py"
    )
    task_dir = ROOT / "benchmark/tasks/urine-output-rate/mimic-urine-output-rate-raw"
    config = preflight.load_task_config(task_dir)
    drop_tables = set(config["database"]["drop_tables"])

    assert (
        preflight.RAW_TASK_REQUIRED_DROPS["mimic-urine-output-rate-raw"] <= drop_tables
    )


def test_preflight_skill_snapshots_have_no_target_leakage():
    preflight = _load_module("benchmark_preflight_skills", "benchmark/preflight.py")

    result = preflight.check_skill_snapshots()

    assert result.ok, result.details


def test_preflight_external_view_sources_are_present(monkeypatch, tmp_path):
    preflight = _load_module(
        "benchmark_preflight_external_views", "benchmark/preflight.py"
    )
    agent_db_dir = tmp_path / "agent_db"
    parquet_path = (
        tmp_path / "m4_data" / "parquet" / "mimic-iv" / "hosp" / "admissions.parquet"
    )
    db_path = agent_db_dir / "mimic_test.duckdb"
    agent_db_dir.mkdir()
    parquet_path.parent.mkdir(parents=True)

    con = duckdb.connect(str(db_path))
    try:
        con.execute(
            f"COPY (SELECT 1 AS subject_id) TO '{parquet_path.as_posix()}' "
            "(FORMAT PARQUET)"
        )
        con.execute(
            "CREATE VIEW admissions AS SELECT * FROM "
            f"read_parquet('{parquet_path.as_posix()}')"
        )
    finally:
        con.close()
    monkeypatch.setattr(preflight, "AGENT_DB_DIR", agent_db_dir)

    result = preflight.check_external_view_sources()

    assert result.ok, result.details
    assert "bench.sh mounts only required Parquet sources" in result.details[0]


def test_preflight_results_root_requires_fresh_directory(tmp_path):
    preflight = _load_module("benchmark_preflight_results", "benchmark/preflight.py")

    existing = tmp_path / "paper"
    run_dir = existing / "run"
    run_dir.mkdir(parents=True)
    (run_dir / "result.json").write_text("{}")

    result = preflight.check_results_root(str(existing))

    assert not result.ok
    assert "already contains" in result.details[0]


def test_preflight_can_run_lightweight_checks_without_local_dbs(tmp_path):
    preflight = _load_module(
        "benchmark_preflight_lightweight", "benchmark/preflight.py"
    )

    results = preflight.run_checks(
        results_root=str(tmp_path / "fresh"),
        check_dbs=False,
        self_check_ground_truth=False,
    )

    assert all(result.ok for result in results), [r for r in results if not r.ok]
