from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _reset_task_globals(matrix):
    matrix.ALL_TASKS.clear()
    matrix.STANDARD_TASKS.clear()
    matrix.RAW_TASKS.clear()
    matrix.EXPERT_TASKS.clear()
    matrix.COMPOSITIONAL_TASKS.clear()
    matrix.CROSS_DB_TASKS.clear()
    matrix.CONTAMINATION_TASKS.clear()


def test_build_tiers_uses_agent_specific_codex_models():
    matrix = _load_module("benchmark_matrix_codex", "benchmark/matrix.py")
    _reset_task_globals(matrix)
    matrix._classify_tasks()

    tiers = matrix.build_tiers(seeds=1, agent="codex")
    models = {run["model"] for tier in tiers for run in tier.runs}

    assert models == {"gpt-5.5", "gpt-5.4-mini"}


def test_default_profile_is_audited_v1_1_alias():
    matrix = _load_module("benchmark_matrix_default_profile", "benchmark/matrix.py")
    _reset_task_globals(matrix)
    matrix._classify_tasks()

    default_tiers = matrix.build_tiers(seeds=1, agent="codex")
    explicit_tiers = matrix.build_tiers(seeds=1, agent="codex", profile="rerun-v1.1")

    default_runs = [run for tier in default_tiers for run in tier.runs]
    explicit_runs = [run for tier in explicit_tiers for run in tier.runs]
    assert matrix.DEFAULT_PROFILE == "rerun-v1.1"
    assert default_runs == explicit_runs


def _seed_contamination_db_markers(matrix, tmp_path: Path, task_names: list[str]):
    matrix.AGENT_DB_DIR = tmp_path
    for task_name in task_names:
        task_key = task_name.replace("mimic-", "").replace("eicu-", "")
        (tmp_path / f"obfuscated_{task_key}.duckdb").touch()
        (tmp_path / f"restructured_{task_key}.duckdb").touch()


def test_provider_comparison_profile_uses_requested_seeds_for_claude(tmp_path):
    matrix = _load_module("benchmark_matrix_provider_comparison", "benchmark/matrix.py")
    _seed_contamination_db_markers(
        matrix,
        tmp_path,
        [
            "mimic-sofa-24h-raw",
            "mimic-kdigo-48h-raw",
            "mimic-oasis-24h-raw",
        ],
    )
    _reset_task_globals(matrix)
    matrix._classify_tasks()

    tiers = matrix.build_tiers(seeds=5, agent="claude", profile="provider-comparison")

    assert sum(len(tier.runs) for tier in tiers) == 190
    assert {run["model"] for tier in tiers for run in tier.runs} == {"opus", "sonnet"}
    assert {run["condition"] for run in tiers[0].runs} == {"no-skill", "with-skill"}
    assert {run["trial"] for tier in tiers for run in tier.runs} == {1, 2, 3, 4, 5}


def test_filter_existing_skips_completed_trial_ids():
    matrix = _load_module("benchmark_matrix_filter_existing", "benchmark/matrix.py")
    runs = [
        {
            "task": "mimic-sofa-24h",
            "condition": "no-skill",
            "model": "gpt-5.5",
            "schema": "native",
            "trial": 1,
        },
        {
            "task": "mimic-sofa-24h",
            "condition": "no-skill",
            "model": "gpt-5.5",
            "schema": "native",
            "trial": 2,
        },
    ]
    existing = {
        matrix._cell_key(
            "mimic-sofa-24h",
            "no-skill",
            "gpt-5.5",
            "native",
            "medium",
        ): {1, 2}
    }

    assert matrix._filter_existing(runs, existing, "medium") == []


def test_filter_existing_resumes_missing_non_prefix_trial():
    matrix = _load_module("benchmark_matrix_filter_non_prefix", "benchmark/matrix.py")
    runs = [
        {
            "task": "mimic-sofa-24h",
            "condition": "no-skill",
            "model": "gpt-5.5",
            "schema": "native",
            "trial": trial,
        }
        for trial in [1, 2, 3]
    ]
    existing = {
        matrix._cell_key(
            "mimic-sofa-24h",
            "no-skill",
            "gpt-5.5",
            "native",
            "medium",
        ): {1, 3}
    }

    filtered = matrix._filter_existing(runs, existing, "medium")

    assert [run["trial"] for run in filtered] == [2]


def test_scan_existing_tracks_completed_trial_ids(tmp_path):
    matrix = _load_module("benchmark_matrix_scan_existing", "benchmark/matrix.py")
    result_dir = tmp_path / "run"
    result_dir.mkdir()
    (result_dir / "output.csv").write_text("stay_id,score\n1,0\n")
    (result_dir / "trace.jsonl").write_text("{}\n")
    (result_dir / "result.json").write_text(
        json.dumps(
            {
                "task": "mimic-sofa-24h",
                "condition": "no-skill",
                "model": "gpt-5.5",
                "schema": "native",
                "resolved_reasoning_effort": "medium",
                "trial": 2,
                "publishable": True,
                "agent_result": {"returncode": 0},
                "agent_db": {
                    "path": "/benchmark/agent_db/example.duckdb",
                    "sha256": "abc",
                },
                "filesystem_canary": {"passed": True},
                "contamination_lint": {"passed": True},
                "test_results": {"reward": 0.0, "errors": 0},
            }
        )
    )

    existing = matrix._scan_existing(tmp_path)

    assert existing[
        matrix._cell_key(
            "mimic-sofa-24h",
            "no-skill",
            "gpt-5.5",
            "native",
            "medium",
        )
    ] == {2}


def test_scan_existing_ignores_non_publishable_or_failed_runs(tmp_path):
    matrix = _load_module(
        "benchmark_matrix_scan_existing_invalid", "benchmark/matrix.py"
    )

    base = {
        "task": "mimic-sofa-24h",
        "condition": "no-skill",
        "model": "gpt-5.5",
        "schema": "native",
        "resolved_reasoning_effort": "medium",
        "trial": 1,
        "test_results": {"reward": 1.0, "errors": 0},
        "filesystem_canary": {"passed": True},
        "contamination_lint": {"passed": True},
        "agent_result": {"returncode": 0},
        "agent_db": {"path": "/benchmark/agent_db/example.duckdb", "sha256": "abc"},
    }
    cases = [
        {"publishable": False},
        {"publishable": True, "agent_result": {"failure_reason": "auth"}},
        {"publishable": True, "agent_result": {"returncode": -1}},
        {"publishable": True, "test_results": {"reward": 0.0, "errors": 1}},
        {"publishable": True, "agent_db": {}},
        {"publishable": True, "filesystem_canary": {"passed": False}},
        {"publishable": True, "contamination_lint": {"passed": False}},
    ]
    for i, override in enumerate(cases):
        run_dir = tmp_path / f"run{i}"
        run_dir.mkdir()
        data = {**base, **override}
        (run_dir / "result.json").write_text(json.dumps(data))

    assert matrix._scan_existing(tmp_path) == {}


def test_filter_existing_keeps_legacy_runs_separate_from_pinned_reasoning():
    matrix = _load_module("benchmark_matrix_filter_reasoning", "benchmark/matrix.py")
    runs = [
        {
            "task": "mimic-sofa-24h",
            "condition": "no-skill",
            "model": "gpt-5.5",
            "schema": "native",
            "trial": 1,
        }
    ]
    existing = {"mimic-sofa-24h|no-skill|gpt-5.5|native|legacy-default": {1}}

    assert matrix._filter_existing(runs, existing, "medium") == runs


def test_build_tiers_uses_agent_specific_gemini_models():
    matrix = _load_module("benchmark_matrix_gemini", "benchmark/matrix.py")
    _reset_task_globals(matrix)
    matrix._classify_tasks()

    tiers = matrix.build_tiers(seeds=1, agent="gemini")
    models = {run["model"] for tier in tiers for run in tier.runs}

    assert "gemini-3.1-pro-preview" in models
    assert "gemini-3-flash-preview" in models
    assert "opus" not in models
    assert "sonnet" not in models


def test_build_tiers_uses_agent_specific_pi_ollama_models():
    matrix = _load_module("benchmark_matrix_pi_ollama", "benchmark/matrix.py")
    _reset_task_globals(matrix)
    matrix._classify_tasks()

    tiers = matrix.build_tiers(seeds=1, agent="pi-ollama")
    models = {run["model"] for tier in tiers for run in tier.runs}

    assert models == {"qwen3:4b"}


def test_container_results_root_maps_under_benchmark_root():
    matrix = _load_module("benchmark_matrix_container_root", "benchmark/matrix.py")
    results_root = (ROOT / "benchmark" / "results" / "paper-smoke").resolve()

    assert (
        matrix._container_results_root(results_root) == "/benchmark/results/paper-smoke"
    )


def test_container_results_root_rejects_outside_benchmark_root(tmp_path):
    matrix = _load_module(
        "benchmark_matrix_container_root_error", "benchmark/matrix.py"
    )

    try:
        matrix._container_results_root(tmp_path / "outside")
    except ValueError as exc:
        assert "--results-root must live inside benchmark/" in str(exc)
    else:
        raise AssertionError("expected ValueError for results root outside benchmark/")


def test_run_via_bench_builds_publishable_command(monkeypatch):
    matrix = _load_module("benchmark_matrix_run_via_bench", "benchmark/matrix.py")

    results_root = (ROOT / "benchmark" / "results" / "paper-smoke").resolve()
    run = {"task": "mimic-kdigo-48h", "trial": 2}
    seen = {}

    def fake_subprocess_run(cmd, cwd=None, env=None):
        seen["cmd"] = cmd
        seen["cwd"] = cwd
        seen["env"] = env
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(matrix.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(
        matrix,
        "_find_latest_result",
        lambda *args, **kwargs: {"test_results": {"reward": 1.0}},
    )

    result = matrix._run_via_bench(
        run,
        condition="with-skill",
        model="gpt-5-codex",
        schema="native",
        agent="codex",
        results_root=results_root,
        reasoning_effort="medium",
        max_retries=2,
        retry_delay_seconds=30,
    )

    assert result["test_results"]["reward"] == 1.0
    assert seen["cmd"][:2] == ["bash", str(ROOT / "benchmark" / "bench.sh")]
    assert "--task" in seen["cmd"]
    assert "mimic-kdigo-48h" in seen["cmd"]
    assert "--results-root" in seen["cmd"]
    assert "/benchmark/results/paper-smoke" in seen["cmd"]
    assert "--reasoning-effort" in seen["cmd"]
    assert "medium" in seen["cmd"]
    assert seen["env"]["M4BENCH_CONTAINER_NAME"].startswith("m4bench-codex-")


def test_run_via_bench_can_skip_per_run_preflight(monkeypatch):
    matrix = _load_module("benchmark_matrix_run_via_bench_skip", "benchmark/matrix.py")

    results_root = (ROOT / "benchmark" / "results" / "paper-smoke").resolve()
    run = {"task": "mimic-kdigo-48h", "trial": 2}
    seen = {}

    def fake_subprocess_run(cmd, cwd=None, env=None):
        seen["env"] = env
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(matrix.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(
        matrix,
        "_find_latest_result",
        lambda *args, **kwargs: {"test_results": {"reward": 1.0}},
    )

    matrix._run_via_bench(
        run,
        condition="with-skill",
        model="gpt-5-codex",
        schema="native",
        agent="codex",
        results_root=results_root,
        skip_preflight=True,
    )

    assert seen["env"]["M4BENCH_SKIP_PREFLIGHT"] == "1"


def test_run_via_bench_fails_when_no_result_file(monkeypatch):
    matrix = _load_module(
        "benchmark_matrix_run_via_bench_no_result", "benchmark/matrix.py"
    )

    results_root = (ROOT / "benchmark" / "results" / "paper-smoke").resolve()
    run = {"task": "mimic-kdigo-48h", "trial": 2}

    monkeypatch.setattr(
        matrix.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=2),
    )
    monkeypatch.setattr(matrix, "_find_latest_result", lambda *args, **kwargs: None)

    try:
        matrix._run_via_bench(
            run,
            condition="with-skill",
            model="gpt-5-codex",
            schema="native",
            agent="codex",
            results_root=results_root,
            reasoning_effort="medium",
            max_retries=2,
            retry_delay_seconds=30,
        )
    except RuntimeError as exc:
        assert "bench.sh failed" in str(exc)
        assert "exit code 2" in str(exc)
    else:
        raise AssertionError("expected missing result.json to fail")


def test_schedule_runs_prioritizes_slow_tasks():
    matrix = _load_module("benchmark_matrix_schedule", "benchmark/matrix.py")
    runs = [
        {
            "task": "mimic-oasis-24h",
            "condition": "with-skill",
            "model": "gpt-5.5",
            "schema": "native",
            "trial": 1,
        },
        {
            "task": "mimic-sepsis3-raw",
            "condition": "no-skill",
            "model": "gpt-5.5",
            "schema": "native",
            "trial": 1,
        },
        {
            "task": "mimic-urine-output-rate-raw",
            "condition": "with-skill",
            "model": "gpt-5.5",
            "schema": "native",
            "trial": 1,
        },
    ]

    scheduled = matrix._schedule_runs(runs)

    assert [run["task"] for run in scheduled] == [
        "mimic-sepsis3-raw",
        "mimic-urine-output-rate-raw",
        "mimic-oasis-24h",
    ]


def test_run_tier_parallel_uses_global_scheduled_queue(monkeypatch, tmp_path):
    matrix = _load_module("benchmark_matrix_global_queue", "benchmark/matrix.py")
    tier = matrix.Tier(1, "test", "question")
    tier.runs = [
        {
            "task": "mimic-oasis-24h",
            "condition": "with-skill",
            "model": "gpt-5.5",
            "schema": "native",
            "trial": 1,
        },
        {
            "task": "mimic-sepsis3-raw",
            "condition": "no-skill",
            "model": "gpt-5.4-mini",
            "schema": "native",
            "trial": 1,
        },
    ]
    seen = {}

    def fake_run_runs_parallel(runs, *args, **kwargs):
        seen["runs"] = runs

    monkeypatch.setattr(matrix, "_run_runs_parallel", fake_run_runs_parallel)

    matrix._run_tier(
        tier,
        parallel=2,
        skip_existing=False,
        dry_run=False,
        no_isolation=False,
        results_root=tmp_path,
    )

    assert [run["task"] for run in seen["runs"]] == [
        "mimic-sepsis3-raw",
        "mimic-oasis-24h",
    ]
