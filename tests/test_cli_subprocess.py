import json
import os
import subprocess
import sys
from pathlib import Path

import duckdb

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
    assert result.stderr.strip() == ""
    assert not any(fragment in stdout for fragment in RICH_FRAGMENTS)
    return payload


def test_status_json_subprocess_is_parseable(tmp_path):
    result = _run_m4(["status", "--json"], tmp_path)

    assert result.returncode == 0
    payload = _assert_single_json_stdout(result)
    assert payload["version"] == 1
    assert "ok" not in payload


def test_status_json_hides_paths_by_default(tmp_path):
    result = _run_m4(["status", "--all", "--json"], tmp_path)

    assert result.returncode == 0
    payload = _assert_single_json_stdout(result)
    assert "parquet_root" not in payload["datasets"][0]
    assert "db_path" not in payload["datasets"][0]
    assert str(tmp_path) not in result.stdout


def test_status_json_paths_flag_discloses_paths(tmp_path):
    result = _run_m4(["status", "--all", "--json", "--paths"], tmp_path)

    assert result.returncode == 0
    payload = _assert_single_json_stdout(result)
    assert "parquet_root" in payload["datasets"][0]
    assert "db_path" in payload["datasets"][0]


def test_status_all_json_subprocess_is_parseable(tmp_path):
    result = _run_m4(["status", "--all", "--json"], tmp_path)

    assert result.returncode == 0
    payload = _assert_single_json_stdout(result)
    assert payload["version"] == 1
    assert {dataset["name"] for dataset in payload["datasets"]} >= {
        "mimic-iv-demo",
        "mimic-iv",
    }


def test_agent_env_json_subprocess_is_parseable(tmp_path):
    result = _run_m4(
        [
            "agent-env",
            "--dataset",
            "mimic-iv-demo",
            "--backend",
            "duckdb",
            "--json",
        ],
        tmp_path,
    )

    assert result.returncode == 0
    payload = _assert_single_json_stdout(result)
    assert payload["ok"] is True
    assert payload["command"] == "agent-env"
    assert payload["context"]["dataset"] == "mimic-iv-demo"
    assert payload["data"]["environment"]["M4_DATA_DIR"] == str(tmp_path / "m4_data")
    assert payload["data"]["raw_paths_hidden"] is True


def test_agent_env_protected_mode_omits_data_dir(tmp_path):
    result = _run_m4(
        ["agent-env", "--mode", "protected", "--json"],
        tmp_path,
    )

    assert result.returncode == 0
    payload = _assert_single_json_stdout(result)
    assert payload["ok"] is True
    assert "M4_DATA_DIR" not in payload["data"]["environment"]
    assert payload["warnings"]


def test_list_datasets_json_subprocess_is_parseable(tmp_path):
    result = _run_m4(["list-datasets", "--json", "--no-interactive"], tmp_path)

    assert result.returncode == 0
    payload = _assert_single_json_stdout(result)
    assert payload["ok"] is True
    assert payload["command"] == "list-datasets"
    assert payload["data"]["raw_paths_hidden"] is True
    assert {dataset["name"] for dataset in payload["data"]["datasets"]} >= {
        "mimic-iv-demo",
        "mimic-iv",
    }


def test_schema_json_error_redacts_data_dir(tmp_path):
    result = _run_m4(
        [
            "schema",
            "--dataset",
            "mimic-iv-demo",
            "--backend",
            "duckdb",
            "--json",
            "--no-interactive",
        ],
        tmp_path,
    )

    assert result.returncode != 0
    payload = _assert_single_json_stdout(result)
    assert payload["ok"] is False
    assert payload["command"] == "schema"
    assert "<M4_DATA_DIR>" in payload["error"]["message"]
    assert str(tmp_path) not in result.stdout


def test_query_json_subprocess_returns_stable_envelope(tmp_path):
    db_path = tmp_path / "m4_data" / "databases" / "mimic_iv_demo.duckdb"
    db_path.parent.mkdir(parents=True)
    conn = duckdb.connect(str(db_path))
    conn.close()

    result = _run_m4(
        [
            "query",
            "--dataset",
            "mimic-iv-demo",
            "--backend",
            "duckdb",
            "--sql",
            "SELECT 1 AS one",
            "--json",
            "--no-interactive",
        ],
        tmp_path,
    )

    assert result.returncode == 0
    payload = _assert_single_json_stdout(result)
    assert payload["ok"] is True
    assert payload["command"] == "query"
    assert payload["context"]["dataset"] == "mimic-iv-demo"
    assert payload["data"]["result"]["columns"] == ["one"]
    assert payload["data"]["result"]["rows"] == [{"one": 1}]


def test_query_json_subprocess_serializes_date_timestamp_and_null(tmp_path):
    db_path = tmp_path / "m4_data" / "databases" / "mimic_iv_demo.duckdb"
    db_path.parent.mkdir(parents=True)
    conn = duckdb.connect(str(db_path))
    conn.close()

    result = _run_m4(
        [
            "query",
            "--dataset",
            "mimic-iv-demo",
            "--backend",
            "duckdb",
            "--sql",
            (
                "SELECT DATE '2026-05-29' AS event_date, "
                "TIMESTAMP '2026-05-29 12:34:56' AS event_time, "
                "NULL AS missing_value"
            ),
            "--json",
            "--no-interactive",
        ],
        tmp_path,
    )

    assert result.returncode == 0
    payload = _assert_single_json_stdout(result)
    assert payload["ok"] is True
    row = payload["data"]["result"]["rows"][0]
    assert row == {
        "event_date": "2026-05-29T00:00:00",
        "event_time": "2026-05-29T12:34:56",
        "missing_value": None,
    }


def test_provenance_export_json_subprocess_is_parseable(tmp_path):
    result = _run_m4(["provenance", "export", "--json"], tmp_path)

    assert result.returncode == 0
    payload = _assert_single_json_stdout(result)
    assert payload["ok"] is True
    assert payload["command"] == "provenance export"
    assert payload["data"]["event_count"] == 0


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


def test_init_json_subprocess_missing_credentialed_raw_files_is_parseable(tmp_path):
    result = _run_m4(["init", "mimic-iv", "--json"], tmp_path)

    assert result.returncode != 0
    payload = _assert_single_json_stdout(result)
    assert payload["ok"] is False
    assert payload["command"] == "init"
    assert payload["error"]["code"] == "raw_files_missing"
