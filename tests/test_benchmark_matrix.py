from __future__ import annotations

import importlib.util
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

    assert models == {"gpt-5-codex"}


def test_build_tiers_uses_agent_specific_gemini_models():
    matrix = _load_module("benchmark_matrix_gemini", "benchmark/matrix.py")
    _reset_task_globals(matrix)
    matrix._classify_tasks()

    tiers = matrix.build_tiers(seeds=1, agent="gemini")
    models = {run["model"] for tier in tiers for run in tier.runs}

    assert "gemini-2.5-pro" in models
    assert "gemini-2.5-flash" in models
    assert "opus" not in models
    assert "sonnet" not in models
    assert "haiku" not in models


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
        max_retries=2,
        retry_delay_seconds=30,
    )

    assert result["test_results"]["reward"] == 1.0
    assert seen["cmd"][:2] == ["bash", str(ROOT / "benchmark" / "bench.sh")]
    assert "--task" in seen["cmd"]
    assert "mimic-kdigo-48h" in seen["cmd"]
    assert "--results-root" in seen["cmd"]
    assert "/benchmark/results/paper-smoke" in seen["cmd"]
    assert seen["env"]["M4BENCH_CONTAINER_NAME"].startswith("m4bench-codex-")
