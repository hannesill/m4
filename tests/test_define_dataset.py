"""`m4 define-dataset`: a custom dataset inferred from a folder of CSV.gz files."""

import gzip
import json
from pathlib import Path

import pytest
from typer.main import get_command

import m4.config as cfg_mod
from m4.cli import app
from m4.core.datasets import DatasetRegistry, Modality
from m4.services.capabilities import build_capabilities_manifest
from m4.services.define_dataset import define_dataset_service
from m4.services.results import CommandError, CommandResult


@pytest.fixture
def datasets_dir(tmp_path, monkeypatch):
    """The custom datasets folder of a throwaway M4 data directory."""
    folder = tmp_path / "m4_data" / "datasets"
    monkeypatch.setattr(cfg_mod, "_CUSTOM_DATASETS_DIR", folder)
    DatasetRegistry.reset()
    yield folder
    DatasetRegistry.reset()


def _export(root: Path, *names: str) -> Path:
    """A folder holding a small CSV.gz file at each of `names`."""
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if name.endswith(".gz"):
            with gzip.open(path, "wt", encoding="utf-8") as handle:
                handle.write("id\n1\n")
        else:
            path.write_text("id\n1\n")
    return root


def _define(name: str, src: Path, **options) -> CommandResult:
    result = define_dataset_service(name, str(src), **options)
    assert isinstance(result, CommandResult), result
    return result


def _refused(name: str, src: Path, **options) -> CommandError:
    result = define_dataset_service(name, str(src), **options)
    assert isinstance(result, CommandError), result
    return result


# ------------------------------------------------------------
# What the folder becomes
# ------------------------------------------------------------


def test_files_in_the_folder_get_a_schema_named_after_the_dataset(
    datasets_dir, tmp_path
):
    src = _export(tmp_path / "export", "admissions.csv.gz", "Patients.csv.gz")

    data = _define("study.2024", src).data

    assert data["definition"]["schema_mapping"] == {"": "study_2024"}
    assert data["tables"] == ["study_2024.admissions", "study_2024.patients"]
    assert data["schemas"] == {"study_2024": 2}
    assert data["primary_verification_table"] == "study_2024.admissions"


def test_root_schema_is_not_named_like_the_database(datasets_dir, tmp_path):
    # my-export.duckdb is the database `my_export`; a schema of that name would
    # make `my_export.admissions` ambiguous.
    src = _export(tmp_path / "export", "admissions.csv.gz")

    data = _define("my-export", src).data

    assert data["definition"]["schema_mapping"] == {"": "my_export_data"}


def test_each_subfolder_gets_its_own_schema(datasets_dir, tmp_path):
    src = _export(
        tmp_path / "export",
        "Lab Results/chemistry.csv.gz",
        "vitals/heart_rate.csv.gz",
        "vitals/blood_pressure.csv.gz",
    )

    data = _define("my-export", src).data

    assert data["definition"]["schema_mapping"] == {
        "Lab Results": "lab_results",
        "vitals": "vitals",
    }
    assert data["schemas"] == {"lab_results": 1, "vitals": 2}
    assert data["table_count"] == 3
    assert data["primary_verification_table"] == "lab_results.chemistry"


def test_files_in_the_folder_and_in_subfolders(datasets_dir, tmp_path):
    src = _export(tmp_path / "export", "patients.csv.gz", "labs/chemistry.csv.gz")

    data = _define("cohort", src).data

    assert data["definition"]["schema_mapping"] == {"": "cohort_data", "labs": "labs"}
    assert data["tables"] == ["cohort_data.patients", "labs.chemistry"]


@pytest.mark.parametrize(
    ("folder", "schema"),
    [
        ("2024 Labs", "_2024_labs"),  # no leading digit, no space
        ("Vital-Signs.v2", "vital_signs_v2"),
        ("order", "order_"),  # a reserved word cannot name a schema
        ("cohort", "cohort_data"),  # the database of dataset `cohort`
        # DuckDB's own schemas and catalogs
        ("main", "main_data"),
        ("information_schema", "information_schema_data"),
        ("pg_catalog", "pg_catalog_data"),
        ("temp", "temp_data"),
        ("system", "system_data"),
    ],
)
def test_subfolder_names_become_sql_identifiers(datasets_dir, tmp_path, folder, schema):
    src = _export(tmp_path / "export", f"{folder}/chemistry.csv.gz")

    data = _define("cohort", src).data

    assert data["definition"]["schema_mapping"] == {folder: schema}


def test_renamed_schema_still_cannot_take_another_folder_s_table(
    datasets_dir, tmp_path
):
    src = _export(tmp_path / "export", "main/a.csv.gz", "main_data/a.csv.gz")

    error = _refused("cohort", src)

    assert error.code == "table_name_collision"


def test_definition_describes_a_local_dataset(datasets_dir, tmp_path):
    src = _export(tmp_path / "export", "admissions.csv.gz")

    definition = _define(
        "cohort", src, title=" My cohort ", summary="Adult ICU stays."
    ).data["definition"]

    assert definition["title"] == "My cohort"
    assert definition["summary"] == "Adult ICU stays."
    assert definition["version"] is None
    assert definition["defined_from"] == str(src.resolve())
    assert definition["modalities"] == ["TABULAR"]
    assert definition["requires_authentication"] is False
    assert definition["bigquery_project_id"] is None
    assert definition["bigquery_dataset_ids"] == []
    assert "file_listing_url" not in definition


def test_saved_definition_loads_into_a_fresh_registry(datasets_dir, tmp_path):
    src = _export(tmp_path / "export", "admissions.csv.gz", "labs/chemistry.csv.gz")
    path = Path(_define("cohort", src).data["definition_path"])

    assert path == datasets_dir / "cohort.json"
    DatasetRegistry.reset()
    DatasetRegistry.load_custom_datasets(datasets_dir)

    ds = DatasetRegistry.get("cohort")
    assert ds.schema_mapping == {"": "cohort_data", "labs": "labs"}
    assert ds.primary_verification_table == "cohort_data.admissions"
    assert ds.defined_from == str(src.resolve())
    assert ds.title == "cohort"
    assert ds.summary is None
    assert ds.version is None
    assert ds.modalities == frozenset({Modality.TABULAR})
    assert ds.bigquery_project_id is None
    assert not DatasetRegistry.is_builtin("cohort")


def test_definition_is_registered_in_the_running_process(datasets_dir, tmp_path):
    src = _export(tmp_path / "export", "admissions.csv.gz")

    _define("cohort", src)

    assert DatasetRegistry.get("cohort").defined_from == str(src.resolve())


def test_dry_run_writes_nothing(datasets_dir, tmp_path):
    src = _export(tmp_path / "export", "admissions.csv.gz")

    data = _define("cohort", src, dry_run=True).data

    assert data["dry_run"] is True
    assert data["definition_path"] == str(datasets_dir / "cohort.json")
    assert data["tables"] == ["cohort_data.admissions"]
    assert not datasets_dir.exists()
    assert DatasetRegistry.get("cohort") is None


def test_plain_and_gzipped_csv_files_both_become_tables(datasets_dir, tmp_path):
    src = _export(
        tmp_path / "export", "admissions.csv.gz", "notes.csv", "labs/chem.csv"
    )

    result = _define("cohort", src)

    assert result.data["tables"] == [
        "cohort_data.admissions",
        "cohort_data.notes",
        "labs.chem",
    ]
    assert result.warnings == []


# ------------------------------------------------------------
# What it refuses
# ------------------------------------------------------------


@pytest.mark.parametrize("name", ["my cohort", "-cohort", "co/hort", ""])
def test_name_must_be_usable(datasets_dir, tmp_path, name):
    src = _export(tmp_path / "export", "admissions.csv.gz")

    assert _refused(name, src).code == "invalid_dataset_name"


def test_name_of_a_builtin_dataset_is_refused_even_with_force(datasets_dir, tmp_path):
    src = _export(tmp_path / "export", "admissions.csv.gz")

    assert _refused("MIMIC-IV", src, force=True).code == "builtin_dataset"
    assert not datasets_dir.exists()


def test_folder_must_exist_and_be_a_folder(datasets_dir, tmp_path):
    src = _export(tmp_path / "export", "admissions.csv.gz")

    assert _refused("cohort", tmp_path / "missing").code == "source_not_found"
    assert (
        _refused("cohort", src / "admissions.csv.gz").code == "source_not_a_directory"
    )


def test_plain_and_gzipped_file_of_one_name_are_the_same_table(datasets_dir, tmp_path):
    src = _export(tmp_path / "export", "labs.csv", "labs.csv.gz")

    error = _refused("cohort", src)

    assert error.code == "table_name_collision"
    assert "labs.csv and labs.csv.gz" in error.message


def test_folder_without_csv_files_is_refused(datasets_dir, tmp_path):
    src = _export(tmp_path / "export", "readme.txt")

    assert _refused("cohort", src).code == "raw_files_missing"


def test_files_deeper_than_one_folder_are_refused(datasets_dir, tmp_path):
    # `m4 init` would convert them but make no table of them.
    src = _export(
        tmp_path / "export", "2024/admissions.csv.gz", "2024/labs/chemistry.csv.gz"
    )

    error = _refused("cohort", src)

    assert error.code == "unsupported_layout"
    assert "2024/labs/chemistry.csv.gz" in error.message
    assert error.hint == f"Choose {(src / '2024').resolve()} instead."


def test_file_name_that_cannot_name_a_table_is_refused(datasets_dir, tmp_path):
    src = _export(tmp_path / "export", "lab results.csv.gz", "2024-labs.csv.gz")

    error = _refused("cohort", src)

    assert error.code == "invalid_table_name"
    assert "lab results.csv.gz" in error.message


def test_files_that_would_become_the_same_table_are_refused(datasets_dir, tmp_path):
    # Both folders become the schema my_labs.
    src = _export(tmp_path / "export", "my-labs/a.csv.gz", "my_labs/a.csv.gz")

    error = _refused("cohort", src)

    assert error.code == "table_name_collision"
    assert "my-labs/a.csv.gz and my_labs/a.csv.gz" in error.message


# ------------------------------------------------------------
# A definition that is already there
# ------------------------------------------------------------


def test_definition_it_wrote_is_replaced_without_flags(datasets_dir, tmp_path):
    wrong = _export(tmp_path / "wrong", "admissions.csv.gz")
    right = _export(tmp_path / "right", "admissions.csv.gz", "patients.csv.gz")
    _define("cohort", wrong)

    data = _define("cohort", right).data

    assert data["replaced"] is True
    saved = json.loads((datasets_dir / "cohort.json").read_text())
    assert saved["defined_from"] == str(right.resolve())
    assert DatasetRegistry.get("cohort").defined_from == str(right.resolve())
    assert [path.name for path in datasets_dir.iterdir()] == ["cohort.json"]


def test_hand_written_definition_is_replaced_only_with_force(datasets_dir, tmp_path):
    src = _export(tmp_path / "export", "admissions.csv.gz")
    datasets_dir.mkdir(parents=True)
    hand_written = {"name": "cohort", "primary_verification_table": "x.y"}
    (datasets_dir / "cohort.json").write_text(json.dumps(hand_written))

    error = _refused("cohort", src)
    dry = _refused("cohort", src, dry_run=True)

    assert error.code == dry.code == "dataset_exists"
    assert json.loads((datasets_dir / "cohort.json").read_text()) == hand_written

    data = _define("cohort", src, force=True).data

    assert data["replaced"] is True
    saved = json.loads((datasets_dir / "cohort.json").read_text())
    assert saved["defined_from"] == str(src.resolve())


def test_definition_of_the_same_name_in_another_file_is_never_replaced(
    datasets_dir, tmp_path
):
    src = _export(tmp_path / "export", "admissions.csv.gz")
    datasets_dir.mkdir(parents=True)
    (datasets_dir / "mine.json").write_text(json.dumps({"name": "Cohort"}))

    error = _refused("cohort", src, force=True)

    assert error.code == "dataset_exists"
    assert "mine.json" in error.message
    assert not (datasets_dir / "cohort.json").exists()


# ------------------------------------------------------------
# How wrappers find it
# ------------------------------------------------------------


def test_capabilities_list_define_dataset_with_its_real_flags():
    commands = {
        item["name"]: item for item in build_capabilities_manifest()["commands"]
    }
    listed = commands["define-dataset"]
    command = get_command(app).commands["define-dataset"]
    options = {opt for param in command.params for opt in param.opts}

    assert listed["mutates"] is True
    assert set(listed["flags"]) <= options
    assert {
        "--src",
        "--title",
        "--summary",
        "--dry-run",
        "--force",
        "--json",
        "--paths",
    } <= set(listed["flags"])
