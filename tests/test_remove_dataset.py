"""`m4 remove-dataset`: M4's own files of a dataset go, and nothing else."""

import gzip
import json
import subprocess
import sys
from pathlib import Path

import pytest
from typer.main import get_command
from typer.testing import CliRunner

import m4.config as cfg_mod
from m4.cli import app
from m4.core.datasets import DatasetRegistry
from m4.services.capabilities import build_capabilities_manifest
from m4.services.define_dataset import define_dataset_service
from m4.services.remove_dataset import remove_dataset_service
from m4.services.results import CommandError, CommandResult

runner = CliRunner()

DEMO_TABLES = {
    "hosp/admissions": "subject_id,hadm_id\n1,100\n",
    "icu/icustays": "subject_id,stay_id\n1,10\n",
}


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """An empty M4 data directory that only this test uses."""
    root = tmp_path / "m4_data"
    monkeypatch.setattr(cfg_mod, "_PROJECT_DATA_DIR", root)
    monkeypatch.setattr(cfg_mod, "_M4_HOME", root)
    monkeypatch.setattr(cfg_mod, "_DEFAULT_DATABASES_DIR", root / "databases")
    monkeypatch.setattr(cfg_mod, "_DEFAULT_PARQUET_DIR", root / "parquet")
    monkeypatch.setattr(cfg_mod, "_CUSTOM_DATASETS_DIR", root / "datasets")
    monkeypatch.setattr(cfg_mod, "_RUNTIME_CONFIG_PATH", root / "config.json")
    for name in ("M4_HOME", "M4_BACKEND", "M4_TELEMETRY_DIR"):
        monkeypatch.delenv(name, raising=False)
    DatasetRegistry.reset()
    yield root
    DatasetRegistry.reset()


def _write(root: Path, tables: dict[str, str]) -> Path:
    for name, text in tables.items():
        path = root / f"{name}.csv.gz"
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            handle.write(text)
    return root


def _init(name: str, *args: str) -> dict:
    result = runner.invoke(app, ["init", name, *args, "--json", "--no-interactive"])
    assert result.exit_code == 0, result.stdout
    return json.loads(result.stdout)


def _listed(name: str) -> dict | None:
    result = runner.invoke(app, ["list-datasets", "--json"])
    datasets = json.loads(result.stdout)["data"]["datasets"]
    return next((item for item in datasets if item["name"] == name), None)


def _remove(name: str, **options) -> dict:
    result = remove_dataset_service(name, **options)
    assert isinstance(result, CommandResult), result
    return result.data


def _files(root: Path) -> list[str]:
    return sorted(str(path) for path in root.rglob("*"))


@pytest.fixture
def custom(data_dir, tmp_path):
    """A dataset defined from a folder of the user's own files, initialized."""
    export = _write(
        tmp_path / "export", {"admissions": "id\n1\n", "labs/chem": "id\n1\n"}
    )
    assert isinstance(define_dataset_service("cohort", str(export)), CommandResult)
    _init("cohort", "--src", str(export))
    return export


def test_builtin_dataset_loses_its_files_and_keeps_its_definition(data_dir):
    _write(data_dir / "raw_files" / "mimic-iv-demo", DEMO_TABLES)
    assert _init("mimic-iv-demo")["prepared"] is True

    data = _remove("mimic-iv-demo")

    database = data_dir / "databases" / "mimic_iv_demo.duckdb"
    assert {item["path"] for item in data["removed"]} == {
        str(database),
        str(database.resolve()) + ".m4-prepared.json",
        str(data_dir / "parquet" / "mimic-iv-demo"),
        str(data_dir / "raw_files" / "mimic-iv-demo"),
    }
    assert data["freed_bytes"] == sum(item["bytes"] for item in data["removed"]) > 0
    assert data["definition_removed"] is False
    assert not database.exists()
    assert not (data_dir / "raw_files" / "mimic-iv-demo").exists()
    listed = _listed("mimic-iv-demo")
    assert listed["setup_state"] == "missing_raw_files"
    assert listed["prepared"] is False


def test_custom_dataset_loses_its_definition_and_keeps_its_source(data_dir, custom):
    before = _files(custom)

    data = _remove("cohort")

    assert data["definition_removed"] is True
    assert str(data_dir / "datasets" / "cohort.json") in {
        item["path"] for item in data["removed"]
    }
    assert data["source_kept"] == str(custom.resolve())
    assert _files(custom) == before  # init --src read the folder in place
    assert not (data_dir / "datasets" / "cohort.json").exists()
    assert not (data_dir / "parquet" / "cohort").exists()
    assert DatasetRegistry.get("cohort") is None
    assert _listed("cohort") is None


def test_keep_definition_removes_only_the_files(data_dir, custom):
    data = _remove("cohort", keep_definition=True)

    assert data["definition_removed"] is False
    assert (data_dir / "datasets" / "cohort.json").exists()
    assert _listed("cohort")["setup_state"] == "missing_raw_files"


def test_dry_run_removes_nothing(data_dir, custom):
    before = _files(data_dir)

    data = _remove("cohort", dry_run=True)

    assert data["dry_run"] is True
    assert data["definition_removed"] is True
    assert len(data["removed"]) == 4  # database, marker, Parquet, definition
    assert _files(data_dir) == before


def test_removing_again_finds_nothing(data_dir, custom):
    _remove("cohort", keep_definition=True)
    _listed("cohort")  # status makes an empty Parquet folder for every dataset

    data = _remove("cohort", keep_definition=True)

    assert data["removed"] == []
    assert data["freed_bytes"] == 0


def test_dataset_with_nothing_on_disk_is_removed_without_error(data_dir):
    data = _remove("eicu")

    assert data["removed"] == [] and data["skipped"] == []


def test_links_out_of_the_data_directory_are_not_followed(data_dir, tmp_path):
    elsewhere = _write(tmp_path / "elsewhere", {"hosp/admissions": "a\n1\n"})
    raw = data_dir / "raw_files" / "mimic-iv-demo"
    _write(raw, {"icu/icustays": "a\n1\n"})
    (raw / "hosp").symlink_to(elsewhere / "hosp")
    (data_dir / "parquet").mkdir(parents=True)
    (data_dir / "parquet" / "mimic-iv-demo").symlink_to(elsewhere)

    data = _remove("mimic-iv-demo")

    # Inside a folder that goes, a link is removed and not followed.
    assert not raw.exists()
    assert (elsewhere / "hosp" / "admissions.csv.gz").exists()
    # A path that leads out of the data directory is not touched at all.
    assert data["skipped"] == [
        {
            "path": str(data_dir / "parquet" / "mimic-iv-demo"),
            "reason": "outside_data_dir",
            "resolves_to": str(elsewhere.resolve()),
        }
    ]
    assert (data_dir / "parquet" / "mimic-iv-demo").is_symlink()


def test_folder_a_dataset_was_defined_from_is_kept_inside_the_data_dir(data_dir):
    own = _write(data_dir / "raw_files" / "cohort", {"admissions": "id\n1\n"})
    assert isinstance(define_dataset_service("cohort", str(own)), CommandResult)

    data = _remove("cohort")

    assert data["skipped"][0]["reason"] == "dataset_source"
    assert (own / "admissions.csv.gz").exists()
    assert data["definition_removed"] is True


def test_database_another_dataset_shares_is_kept(data_dir):
    (data_dir / "datasets").mkdir(parents=True)
    (data_dir / "datasets" / "own.json").write_text(json.dumps({"name": "mimic_iv"}))
    database = data_dir / "databases" / "mimic_iv.duckdb"
    database.parent.mkdir(parents=True)
    database.write_bytes(b"mimic-iv's")

    data = _remove("mimic_iv")

    assert data["skipped"][0]["reason"] == "shared_with_another_dataset"
    assert database.exists()


def test_define_dataset_refuses_a_name_whose_database_is_taken(data_dir, tmp_path):
    export = _write(tmp_path / "export", {"admissions": "id\n1\n"})

    result = define_dataset_service("mimic_iv", str(export))

    assert isinstance(result, CommandError)
    assert result.code == "database_name_taken"


@pytest.mark.parametrize(
    ("name", "code"),
    [("no-such-dataset", "dataset_not_found"), ("../parquet", "invalid_dataset_name")],
)
def test_unknown_or_unusable_name(data_dir, name, code):
    result = remove_dataset_service(name)

    assert isinstance(result, CommandError) and result.code == code


def test_database_another_process_has_open_is_in_use(data_dir, custom):
    database = data_dir / "databases" / "cohort.duckdb"
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import duckdb, sys; con = duckdb.connect(sys.argv[1], read_only=True); "
            "print('open', flush=True); sys.stdin.read()",
            str(database),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout.readline().strip() == "open"

        result = remove_dataset_service("cohort")
    finally:
        holder.communicate("")  # Closing its stdin lets it end

    assert isinstance(result, CommandError)
    assert result.code == "dataset_in_use"
    assert result.data["removed"] == []
    assert database.exists()


def test_json_error_reports_the_code(data_dir):
    result = runner.invoke(app, ["remove-dataset", "nope", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["command"] == "remove-dataset"
    assert payload["error"]["code"] == "dataset_not_found"


def test_capabilities_list_remove_dataset_with_its_real_flags():
    commands = {
        item["name"]: item for item in build_capabilities_manifest()["commands"]
    }
    listed = commands["remove-dataset"]
    command = get_command(app).commands["remove-dataset"]
    options = {opt for param in command.params for opt in param.opts}

    assert listed["mutates"] is True
    assert set(listed["flags"]) == {"--keep-definition", "--dry-run", "--json"}
    assert set(listed["flags"]) <= options
