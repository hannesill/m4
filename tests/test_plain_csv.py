"""Plain .csv files, as researchers export them, become tables like .csv.gz ones."""

import gzip
import json
from pathlib import Path

import duckdb
import pytest
from typer.testing import CliRunner

import m4.config as cfg_mod
from m4.cli import app
from m4.core.datasets import DatasetRegistry
from m4.data_io import _parquet_path_for
from m4.services.define_dataset import define_dataset_service
from m4.services.results import CommandResult

runner = CliRunner()


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


def _export(root: Path, files: dict[str, bytes]) -> Path:
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(gzip.compress(data) if name.endswith(".gz") else data)
    return root


def _define_and_init(src: Path) -> dict:
    assert isinstance(define_dataset_service("cohort", str(src)), CommandResult)
    result = runner.invoke(
        app, ["init", "cohort", "--src", str(src), "--json", "--no-interactive"]
    )
    payload = json.loads(result.stdout)
    assert result.exit_code == (0 if payload["ok"] else 1)
    return payload


def _query(data_dir: Path, sql: str) -> tuple[list[str], list[str], list[tuple]]:
    con = duckdb.connect(str(data_dir / "databases" / "cohort.duckdb"), read_only=True)
    try:
        result = con.execute(sql)
        names = [column[0] for column in result.description]
        types = [str(column[1]) for column in result.description]
        return names, types, result.fetchall()
    finally:
        con.close()


def test_folder_of_excel_exports_becomes_a_dataset(data_dir, tmp_path):
    src = _export(
        tmp_path / "export",
        {
            # Excel's "CSV UTF-8": a byte order mark before the header
            "patients.csv": "﻿id,name\n1,Anna\n2,Ben\n".encode(),
            # A European export: ; between fields
            "labs/chemistry.csv": b"id;test;unit\n1;crea;mg/dl\n2;urea;mg/dl\n",
            # Tab-separated, and gzipped as PhysioNet's files are
            "labs/vitals.csv.gz": b"id\thr\n1\t80\n2\t72\n",
        },
    )

    payload = _define_and_init(src)

    assert payload["prepared"] is True
    assert payload["warnings"] == []
    names, _, rows = _query(
        data_dir,
        "SELECT p.id, p.name, c.test, v.hr FROM cohort_data.patients p "
        "JOIN labs.chemistry c USING (id) JOIN labs.vitals v USING (id) ORDER BY 1",
    )
    assert names == ["id", "name", "test", "hr"]  # no BOM before `id`
    assert rows == [(1, "Anna", "crea", 80), (2, "Ben", "urea", 72)]


def test_latin1_file_is_read_as_latin1_and_says_so(data_dir, tmp_path):
    src = _export(
        tmp_path / "export",
        {"patients.csv": "id;name\n1;René\n2;Zoé\n".encode("latin-1")},
    )

    payload = _define_and_init(src)

    assert payload["ok"] is True
    assert payload["warnings"] == ["csv_read_as_latin1"]
    assert payload["conversion_warnings"] == [
        {"code": "csv_read_as_latin1", "file": str((src / "patients.csv").resolve())}
    ]
    assert _query(data_dir, "SELECT name FROM cohort_data.patients ORDER BY id")[2] == [
        ("René",),
        ("Zoé",),
    ]


def test_utf16_file_with_its_byte_order_mark_is_read(data_dir, tmp_path):
    # Excel's "Unicode Text": UTF-16, tab-separated
    src = _export(
        tmp_path / "export", {"patients.csv": "id\tname\n1\tRené\n".encode("utf-16")}
    )

    payload = _define_and_init(src)

    assert payload["ok"] is True and payload["warnings"] == []
    assert _query(data_dir, "SELECT name FROM cohort_data.patients")[2] == [("René",)]


@pytest.mark.parametrize(
    "text",
    [b"\x93caf\xe9\x94", b"\x80 5"],  # Windows-1252 quotation marks, euro sign
)
def test_windows_1252_text_fails_clearly_instead_of_becoming_controls(
    data_dir, tmp_path, text
):
    # Latin-1 has control characters at 0x80-0x9F, where Windows-1252 has
    # letters. DuckDB's Latin-1 does not decode them, so nothing is stored.
    src = _export(tmp_path / "export", {"notes.csv": b"id;text\n1;" + text + b"\n"})

    payload = _define_and_init(src)

    assert payload["error"]["code"] == "csv_encoding_unsupported"
    assert "notes.csv" in payload["error"]["message"]
    assert "UTF-8" in payload["error"]["hint"]
    assert not list((data_dir / "parquet" / "cohort").rglob("*.parquet"))


def test_decimal_commas_are_kept_as_text_with_a_warning(data_dir, tmp_path):
    src = _export(
        tmp_path / "export",
        {"labs.csv": b"id;value;unit;note\n1;3,5;mg;a,b\n2;4;mg;c\n3;;mg;d\n"},
    )

    payload = _define_and_init(src)

    assert payload["warnings"] == ["decimal_comma_columns_kept_as_text"]
    assert payload["conversion_warnings"][0]["columns"] == ["value"]
    _, types, rows = _query(data_dir, "SELECT value FROM cohort_data.labs ORDER BY id")
    assert types == ["VARCHAR"]
    assert rows == [("3,5",), ("4",), (None,)]


def test_comma_separated_file_is_not_looked_at_for_decimal_commas(data_dir, tmp_path):
    src = _export(tmp_path / "export", {"labs.csv": b'id,value\n1,"3,5"\n'})

    payload = _define_and_init(src)

    assert payload["warnings"] == []


def test_plain_and_gzipped_file_of_one_table_are_refused_by_init(data_dir, tmp_path):
    src = _export(tmp_path / "export", {"labs.csv": b"id\n1\n"})
    assert isinstance(define_dataset_service("cohort", str(src)), CommandResult)
    _export(src, {"labs.csv.gz": b"id\n2\n"})

    result = runner.invoke(
        app, ["init", "cohort", "--src", str(src), "--json", "--no-interactive"]
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"]["code"] == "table_name_collision"


@pytest.mark.parametrize(
    ("raw", "table"),
    [
        ("hosp/admissions.csv.gz", "hosp/admissions.parquet"),
        ("note/discharge.v2.csv.gz", "note/discharge.v2.parquet"),
        ("labs.csv", "labs.parquet"),
        ("labs/chem.v2.csv", "labs/chem.v2.parquet"),
    ],
)
def test_parquet_names_of_gzipped_files_are_unchanged(tmp_path, raw, table):
    assert _parquet_path_for(tmp_path / "raw" / raw, tmp_path / "raw", Path("pq")) == (
        Path("pq") / table
    )
