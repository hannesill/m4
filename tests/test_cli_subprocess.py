import gzip
import json
import os
import subprocess
import sys
from pathlib import Path

import duckdb

import m4

RICH_FRAGMENTS = ["[bold]", "[success]", "__  __", "Medical Data", "─", "│"]


def _run_m4(args: list[str], tmp_path: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(m4.__file__).resolve().parent.parent)
    env["M4_DATA_DIR"] = str(tmp_path / "m4_data")
    env.pop("M4_HOME", None)
    env.pop("M4_BACKEND", None)
    env.pop("M4_DATASET", None)
    env.pop("M4_PROJECT_ID", None)
    env.pop("M4_TELEMETRY_DIR", None)
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


CATALOG_KEYS = {
    "title",
    "summary",
    "version",
    "builtin",
    "modalities",
    "dataset_page_url",
    "download_size_gb",
}


def test_list_datasets_json_describes_each_dataset(tmp_path):
    datasets_dir = tmp_path / "m4_data" / "datasets"
    datasets_dir.mkdir(parents=True)
    (datasets_dir / "described.json").write_text(
        json.dumps(
            {
                "name": "my-icu-extract",
                "title": "My ICU extract",
                "summary": "Adult ICU stays at one hospital.",
                "download_size_gb": 1.5,
                "modalities": ["TABULAR", "NOTES"],
            }
        )
    )
    (datasets_dir / "bare.json").write_text(json.dumps({"name": "bare-extract"}))

    result = _run_m4(["list-datasets", "--json", "--no-interactive"], tmp_path)

    assert result.returncode == 0
    payload = _assert_single_json_stdout(result)
    listed = {dataset["name"]: dataset for dataset in payload["data"]["datasets"]}
    assert all(CATALOG_KEYS <= set(dataset) for dataset in listed.values())

    mimic_iv = listed["mimic-iv"]
    assert mimic_iv["title"] == "MIMIC-IV"
    assert mimic_iv["version"] == "3.1"
    assert mimic_iv["builtin"] is True
    assert mimic_iv["modalities"] == ["TABULAR"]
    assert mimic_iv["dataset_page_url"] == "https://physionet.org/content/mimiciv/"
    assert mimic_iv["summary"]
    assert mimic_iv["download_size_gb"] is None  # PhysioNet shows it only to members
    assert listed["mimic-iv-note"]["modalities"] == ["NOTES"]
    assert listed["eicu-demo"]["download_size_gb"] > 0

    assert {
        "title": "My ICU extract",
        "summary": "Adult ICU stays at one hospital.",
        "version": None,
        "builtin": False,
        "modalities": ["NOTES", "TABULAR"],
        "dataset_page_url": None,
        "download_size_gb": 1.5,
    }.items() <= listed["my-icu-extract"].items()
    assert {
        "title": "bare-extract",
        "summary": None,
        "version": None,
        "builtin": False,
        "modalities": ["TABULAR"],
        "download_size_gb": None,
    }.items() <= listed["bare-extract"].items()


def test_define_dataset_then_init_then_query(tmp_path):
    export = tmp_path / "export"
    (export / "labs").mkdir(parents=True)
    with gzip.open(export / "Patients.csv.gz", "wt") as handle:
        handle.write("patient_id,sex\n1,F\n2,M\n")
    with gzip.open(export / "labs" / "chemistry.csv.gz", "wt") as handle:
        handle.write("patient_id,value\n1,1.1\n")

    defined = _run_m4(
        [
            "define-dataset",
            "My-Export",
            "--src",
            str(export),
            "--title",
            "My export",
            "--json",
        ],
        tmp_path,
    )

    assert defined.returncode == 0
    data = _assert_single_json_stdout(defined)["data"]
    assert data["name"] == "my-export"
    assert data["schemas"] == {"labs": 1, "my_export_data": 1}
    assert data["definition_path"] == str(
        tmp_path / "m4_data" / "datasets" / "my-export.json"
    )

    initialized = _run_m4(
        ["init", "my-export", "--src", str(export), "--no-interactive", "--json"],
        tmp_path,
    )

    assert initialized.returncode == 0
    assert _assert_single_json_stdout(initialized)["prepared"] is True

    queried = _run_m4(
        [
            "query",
            "--dataset",
            "my-export",
            "--sql",
            "SELECT p.sex, c.value FROM my_export_data.patients p "
            "JOIN labs.chemistry c USING (patient_id)",
            "--json",
            "--no-interactive",
        ],
        tmp_path,
    )

    assert queried.returncode == 0
    rows = _assert_single_json_stdout(queried)["data"]["result"]["rows"]
    assert rows == [{"sex": "F", "value": 1.1}]


def test_define_dataset_json_error(tmp_path):
    result = _run_m4(
        ["define-dataset", "eicu", "--src", str(tmp_path), "--json"], tmp_path
    )

    assert result.returncode == 1
    payload = _assert_single_json_stdout(result)
    assert payload["ok"] is False
    assert payload["command"] == "define-dataset"
    assert payload["error"]["code"] == "builtin_dataset"


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

    assert result.returncode == 1
    payload = _assert_single_json_stdout(result)
    assert payload["ok"] is False
    assert payload["command"] == "use"
    assert payload["error"]["code"] == "active_dataset_removed"


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


def test_crash_does_not_print_the_physionet_login(tmp_path):
    """A traceback must not show the login that is in scope when M4 crashes.

    The crash is put where the download would start, so nothing is requested.
    """
    crash_inside_download = """
import sys

import m4.services.download as download_service
from m4.cli import app


def crash(*args, **kwargs):
    raise RuntimeError("simulated crash")


download_service.download_dataset = crash
sys.argv = ["m4", "download", "mimic-iv", "--json", "--physionet-credentials-stdin"]
app()
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(m4.__file__).resolve().parent.parent)
    env["M4_DATA_DIR"] = str(tmp_path / "m4_data")
    for name in ("M4_HOME", "M4_BACKEND", "M4_TELEMETRY_DIR"):
        env.pop(name, None)
    # The traceback as a person or a wrapper gets it by default.
    env.pop("_TYPER_STANDARD_TRACEBACK", None)

    result = subprocess.run(
        [sys.executable, "-c", crash_inside_download],
        input=json.dumps({"username": "fake-user", "password": "FAKE-pw-0123456"}),
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode != 0
    assert "simulated crash" in result.stderr
    for shown in (result.stdout, result.stderr):
        assert "FAKE-pw-0123456" not in shown
        assert "fake-user" not in shown
