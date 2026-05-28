import json
import os
import subprocess
import sys
from pathlib import Path

RICH_FRAGMENTS = ["[bold]", "[success]", "__  __", "Medical Data", "─", "│"]


def _run_m4(args: list[str], tmp_path: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    env["M4_DATA_DIR"] = str(tmp_path / "m4_data")
    env.pop("M4_BACKEND", None)
    env.pop("M4_DATASET", None)
    env.pop("M4_PROJECT_ID", None)
    return subprocess.run(
        [sys.executable, "-m", "m4.cli", *args],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def _assert_single_json_stdout(result: subprocess.CompletedProcess[str]) -> dict:
    stdout = result.stdout.strip()
    payload = json.loads(stdout)
    assert stdout == json.dumps(payload, indent=2)
    assert not any(fragment in stdout for fragment in RICH_FRAGMENTS)
    return payload


def test_status_json_subprocess_is_parseable(tmp_path):
    result = _run_m4(["status", "--json"], tmp_path)

    assert result.returncode == 0
    payload = _assert_single_json_stdout(result)
    assert payload["version"] == 1
    assert "ok" not in payload


def test_status_all_json_subprocess_is_parseable(tmp_path):
    result = _run_m4(["status", "--all", "--json"], tmp_path)

    assert result.returncode == 0
    payload = _assert_single_json_stdout(result)
    assert payload["version"] == 1
    assert {dataset["name"] for dataset in payload["datasets"]} >= {
        "mimic-iv-demo",
        "mimic-iv",
    }


def test_use_json_subprocess_is_parseable(tmp_path):
    pq_root = tmp_path / "m4_data" / "parquet" / "mimic-iv-demo"
    pq_root.mkdir(parents=True)
    (pq_root / "admissions.parquet").touch()

    result = _run_m4(["use", "mimic-iv-demo", "--json"], tmp_path)

    assert result.returncode == 0
    payload = _assert_single_json_stdout(result)
    assert payload["ok"] is True
    assert payload["command"] == "use"
    assert payload["active_dataset"] == "mimic-iv-demo"


def test_backend_json_subprocess_is_parseable(tmp_path):
    result = _run_m4(["backend", "duckdb", "--json"], tmp_path)

    assert result.returncode == 0
    payload = _assert_single_json_stdout(result)
    assert payload["ok"] is True
    assert payload["command"] == "backend"
    assert payload["backend"] == "duckdb"


def test_failing_json_subprocess_emits_one_parseable_error(tmp_path):
    result = _run_m4(["backend", "mysql", "--json"], tmp_path)

    assert result.returncode != 0
    payload = _assert_single_json_stdout(result)
    assert payload["ok"] is False
    assert payload["command"] == "backend"
    assert payload["error"]["code"] == "invalid_backend"


def test_init_json_subprocess_error_is_parseable(tmp_path):
    result = _run_m4(["init", "not-a-dataset", "--json"], tmp_path)

    assert result.returncode != 0
    payload = _assert_single_json_stdout(result)
    assert payload["ok"] is False
    assert payload["command"] == "init"
    assert payload["error"]["code"] == "dataset_not_found"


def test_init_json_subprocess_blocked_state_is_parseable(tmp_path):
    result = _run_m4(["init", "mimic-iv", "--json"], tmp_path)

    assert result.returncode == 0
    payload = _assert_single_json_stdout(result)
    assert payload["ok"] is True
    assert payload["command"] == "init"
    assert payload["dataset"] == "mimic-iv"
    assert payload["steps"][0]["status"] == "blocked"
