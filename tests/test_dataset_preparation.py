"""A dataset is reported ready only when its preparation ran to the end.

These tests run the commands a wrapper drives (`m4 init --json --events ndjson`
and `m4 list-datasets --json`) against a throwaway data directory and a few
rows of made-up CSV.gz data. "Killed" stands in for the process dying, which a
wrapper causes when its user cancels, and which leaves no chance to clean up.
"""

import gzip
import json
import os
import shutil
from pathlib import Path

import duckdb
import pytest
from typer.testing import CliRunner

import m4.config as cfg_mod
from m4.cli import app
from m4.services.events import NdjsonEventReporter

runner = CliRunner()

TABLES = {
    "hosp/admissions": "subject_id,hadm_id\n1,100\n2,200\n",
    "hosp/patients": "subject_id,gender\n1,F\n2,M\n",
    "icu/chartevents": "subject_id,stay_id,valuenum\n1,10,1.5\n2,20,2.5\n3,30,3.5\n",
}
ALL_VIEWS = {
    "mimiciv_hosp.admissions",
    "mimiciv_hosp.patients",
    "mimiciv_icu.chartevents",
}


class Killed(BaseException):
    """The process died here. Nothing below it gets to tidy up."""


def _no_network(*args, **kwargs):
    raise AssertionError("This test must not open a network session.")


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
    monkeypatch.setattr("m4.data_io.requests.Session", _no_network)
    return root


@pytest.fixture
def raw(tmp_path):
    """The folder a researcher points M4 at: hosp/ and icu/ directly inside."""
    return _write_raw(tmp_path / "downloads" / "mimiciv" / "3.1")


def _write_raw(root: Path, tables: dict[str, str] = TABLES) -> Path:
    for name, text in tables.items():
        path = root / f"{name}.csv.gz"
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            handle.write(text)
    return root


def _init(*args: str):
    """Run `m4 init mimic-iv` as a wrapper does and return (result, events)."""
    result = runner.invoke(
        app,
        ["init", "mimic-iv", *args, "--no-interactive", "--json", "--events", "ndjson"],
    )
    events = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    return result, events


def _listed(name: str = "mimic-iv") -> dict:
    """What `m4 list-datasets --json` says about a dataset."""
    result = runner.invoke(app, ["list-datasets", "--json"])
    assert result.exit_code == 0
    datasets = json.loads(result.stdout)["data"]["datasets"]
    return next(dataset for dataset in datasets if dataset["name"] == name)


def _assert_not_ready(listed: dict) -> None:
    assert listed["prepared"] is False
    assert listed["setup_state"] != "ready"


def _assert_ready(listed: dict) -> None:
    assert listed["prepared"] is True
    assert listed["setup_state"] == "ready"


def _database(data_dir: Path, name: str = "mimic-iv") -> Path:
    return data_dir / "databases" / f"{name.replace('-', '_')}.duckdb"


def _parquet(data_dir: Path) -> Path:
    return data_dir / "parquet" / "mimic-iv"


def _views(data_dir: Path, name: str = "mimic-iv") -> set[str]:
    con = duckdb.connect(str(_database(data_dir, name)), read_only=True)
    try:
        rows = con.execute(
            "SELECT table_schema || '.' || table_name FROM information_schema.tables "
            "WHERE table_type = 'VIEW'"
        ).fetchall()
    finally:
        con.close()
    return {row[0] for row in rows}


def _row_count(data_dir: Path, table: str) -> int:
    con = duckdb.connect(str(_database(data_dir)), read_only=True)
    try:
        return con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        con.close()


def _die_before_publishing(monkeypatch, table: str) -> None:
    """Die when `table` is converted but still under its temporary name."""
    real_replace = os.replace

    def replace(src, dst):
        if Path(dst).name == f"{table}.parquet":
            raise Killed()
        return real_replace(src, dst)

    monkeypatch.setattr("m4.data_io.os.replace", replace)


def _die_after_view(monkeypatch, count: int) -> None:
    """Die when `count` views exist."""
    real_emit = NdjsonEventReporter.emit

    def emit(self, event, **fields):
        real_emit(self, event, **fields)
        if event == "duckdb_view_created" and fields["completed"] == count:
            raise Killed()

    monkeypatch.setattr(NdjsonEventReporter, "emit", emit)


def test_init_from_a_raw_folder_makes_the_dataset_ready(data_dir, raw):
    _assert_not_ready(_listed())

    result, events = _init("--src", str(raw))

    assert result.exit_code == 0
    assert events[-1]["event"] == "operation_completed"
    assert events[-1]["result"]["ok"] is True
    assert events[-1]["result"]["prepared"] is True
    started = next(e for e in events if e["event"] == "conversion_started")
    assert (started["file_count"], started["skipped_count"]) == (3, 0)
    assert _views(data_dir) == ALL_VIEWS
    _assert_ready(_listed())


def test_init_again_converts_nothing_and_stays_ready(data_dir, raw):
    _init("--src", str(raw))

    result, events = _init("--src", str(raw))

    assert result.exit_code == 0
    assert not [e for e in events if e["event"].startswith("conversion_")]
    steps = {step["name"]: step["status"] for step in events[-1]["result"]["steps"]}
    assert steps["parquet"] == "skipped"
    assert steps["database"] == "completed"
    _assert_ready(_listed())


def test_conversion_killed_then_init_again_converts_the_missing_table(
    data_dir, raw, monkeypatch
):
    with monkeypatch.context() as dying, pytest.raises(Killed):
        _die_before_publishing(dying, "chartevents")
        _init("--src", str(raw))

    # The table that was in flight is not there under its final name, and the
    # dataset is not ready although Parquet files exist.
    in_flight = _parquet(data_dir) / "icu" / "chartevents.parquet"
    assert not in_flight.exists()
    assert in_flight.with_name("chartevents.parquet.part").exists()
    assert (_parquet(data_dir) / "hosp" / "admissions.parquet").exists()
    _assert_not_ready(_listed())

    result, events = _init("--src", str(raw))

    assert result.exit_code == 0
    started = next(e for e in events if e["event"] == "conversion_started")
    assert (started["file_count"], started["skipped_count"]) == (1, 2)
    converted = [e for e in events if e["event"] == "conversion_file_completed"]
    assert [Path(e["path"]).name for e in converted] == ["chartevents.parquet"]
    assert events[-1]["result"]["prepared"] is True
    assert not list(_parquet(data_dir).rglob("*.part"))
    assert _views(data_dir) == ALL_VIEWS
    assert _row_count(data_dir, "mimiciv_icu.chartevents") == 3
    _assert_ready(_listed())


def test_conversion_killed_then_init_without_the_raw_files_is_refused(
    data_dir, raw, monkeypatch
):
    with monkeypatch.context() as dying, pytest.raises(Killed):
        _die_before_publishing(dying, "chartevents")
        _init("--src", str(raw))

    # Without --src there are no raw files to finish with. Building the
    # database from the tables that happen to exist would hide the missing one.
    result, events = _init()

    assert result.exit_code == 1
    failure = events[-1]
    assert failure["event"] == "operation_failed"
    assert failure["error"]["code"] == "raw_files_missing"
    assert str(raw) in failure["error"]["hint"]
    assert not _database(data_dir).exists()
    _assert_not_ready(_listed())


def test_view_creation_killed_is_not_ready_until_init_runs_again(
    data_dir, raw, monkeypatch
):
    with monkeypatch.context() as dying, pytest.raises(Killed):
        _die_after_view(dying, 1)
        _init("--src", str(raw))

    # Every Parquet file and the database exist, but two tables have no view.
    assert len(list(_parquet(data_dir).rglob("*.parquet"))) == 3
    assert len(_views(data_dir)) == 1
    listed = _listed()
    assert (listed["parquet_present"], listed["db_present"]) == (True, True)
    assert listed["prepared"] is False
    assert listed["setup_state"] == "incomplete"

    result, _ = _init("--src", str(raw))

    assert result.exit_code == 0
    assert _views(data_dir) == ALL_VIEWS
    _assert_ready(_listed())


def test_wget_r_folder_is_refused_and_names_the_folder_to_choose(data_dir, tmp_path):
    # `wget -r` without --cut-dirs and -nH creates physionet.org/files/<name>/<version>/.
    wget_root = tmp_path / "physionet.org"
    version_folder = _write_raw(wget_root / "files" / "mimiciv" / "3.1")

    result, events = _init("--src", str(wget_root))

    assert result.exit_code == 1
    failure = events[-1]
    assert failure["event"] == "operation_failed"
    assert failure["error"]["code"] == "raw_files_missing"
    assert failure["error"]["hint"] == f"Choose {version_folder} instead."
    assert not list(data_dir.rglob("*.parquet"))
    assert not _database(data_dir).exists()
    _assert_not_ready(_listed())

    result, _ = _init("--src", str(version_folder))

    assert result.exit_code == 0
    assert _views(data_dir) == ALL_VIEWS
    _assert_ready(_listed())


def test_wget_r_folder_is_refused_without_json_too(data_dir, tmp_path, monkeypatch):
    wget_root = tmp_path / "physionet.org"
    _write_raw(wget_root / "files" / "mimiciv" / "3.1")
    monkeypatch.setattr("m4.config._find_project_root_from_cwd", Path.cwd)

    result = runner.invoke(app, ["init", "mimic-iv", "--src", str(wget_root)])

    assert result.exit_code == 1
    assert "Cannot Initialize" in result.output
    assert not list(data_dir.rglob("*.parquet"))
    _assert_not_ready(_listed())


def test_folder_without_the_dataset_layout_is_refused(data_dir, tmp_path):
    # MIMIC-IV tables dumped into one folder: M4 cannot tell hosp from icu.
    flat = _write_raw(
        tmp_path / "flat", {"admissions": TABLES["hosp/admissions"], "notes": "a\n1\n"}
    )

    result, events = _init("--src", str(flat))

    assert result.exit_code == 1
    assert events[-1]["error"]["code"] == "raw_files_missing"
    assert (
        events[-1]["error"]["hint"] == "Choose the folder that contains hosp/ and icu/."
    )
    assert not list(data_dir.rglob("*.parquet"))


def test_table_cut_short_under_its_final_name_is_converted_again(data_dir, raw):
    # M4 0.5.5 and earlier wrote tables straight to their final name, so a
    # killed conversion left the start of a Parquet file there.
    _init("--src", str(raw))
    table = _parquet(data_dir) / "icu" / "chartevents.parquet"
    table.write_bytes(table.read_bytes()[:40])

    result, events = _init("--src", str(raw))

    assert result.exit_code == 0
    started = next(e for e in events if e["event"] == "conversion_started")
    assert (started["file_count"], started["skipped_count"]) == (1, 2)
    assert _row_count(data_dir, "mimiciv_icu.chartevents") == 3
    _assert_ready(_listed())


def test_table_cut_short_without_raw_files_fails_with_a_reported_error(data_dir, raw):
    _init("--src", str(raw))
    table = _parquet(data_dir) / "icu" / "chartevents.parquet"
    table.write_bytes(table.read_bytes()[:40])

    result, events = _init()

    assert result.exit_code == 1
    failure = events[-1]
    assert failure["event"] == "operation_failed"
    assert failure["error"]["code"] == "duckdb_init_failed"
    assert "chartevents.parquet" in failure["error"]["message"]
    _assert_not_ready(_listed())


def test_dataset_without_the_prepared_marker_is_not_ready_until_init_runs(
    data_dir, raw
):
    # What M4 0.5.5 and earlier leave: Parquet files and a database, and no
    # record of whether the run that made them finished.
    _init("--src", str(raw))
    _database(data_dir).with_name("mimic_iv.duckdb.m4-prepared.json").unlink()

    listed = _listed()
    assert listed["prepared"] is False
    assert listed["setup_state"] == "incomplete"

    result, _ = _init()

    assert result.exit_code == 0
    _assert_ready(_listed())


def test_tables_added_after_init_are_not_ready_until_init_runs_again(data_dir, raw):
    _init("--src", str(raw))
    parquet = _parquet(data_dir)
    shutil.copy(
        parquet / "hosp" / "patients.parquet", parquet / "hosp" / "extra.parquet"
    )

    _assert_not_ready(_listed())

    result, _ = _init()

    assert result.exit_code == 0
    assert "mimiciv_hosp.extra" in _views(data_dir)
    _assert_ready(_listed())


def test_init_that_finds_the_database_locked_leaves_a_ready_dataset_ready(
    data_dir, raw, monkeypatch
):
    _init("--src", str(raw))

    def locked(*args, **kwargs):
        raise duckdb.IOException("IO Error: Could not set lock on file")

    with monkeypatch.context() as busy:
        busy.setattr("m4.data_io.duckdb.connect", locked)
        result, events = _init("--src", str(raw))

    # Nothing was changed, so the dataset another process is using is intact.
    assert result.exit_code == 1
    assert events[-1]["error"]["code"] == "duckdb_init_failed"
    _assert_ready(_listed())


def test_force_rebuilds_the_database_and_ends_ready(data_dir, raw):
    _init("--src", str(raw))

    result, events = _init("--src", str(raw), "--force")

    assert result.exit_code == 0
    assert events[-1]["result"]["prepared"] is True
    assert _views(data_dir) == ALL_VIEWS
    _assert_ready(_listed())


def test_force_killed_while_recreating_views_is_not_ready(data_dir, raw, monkeypatch):
    _init("--src", str(raw))

    with monkeypatch.context() as dying, pytest.raises(Killed):
        _die_after_view(dying, 1)
        _init("--src", str(raw), "--force")

    assert len(_views(data_dir)) == 1
    _assert_not_ready(_listed())


def test_status_json_reports_prepared_like_list_datasets(data_dir, raw):
    _init("--src", str(raw))

    result = runner.invoke(app, ["status", "--dataset", "mimic-iv", "--json"])

    assert result.exit_code == 0
    dataset = json.loads(result.stdout)["datasets"][0]
    assert dataset["prepared"] is True
    assert dataset["setup_state"] == "ready"
    assert dataset["row_count"] == 2


def test_status_for_people_does_not_call_an_unfinished_dataset_ok(
    data_dir, raw, monkeypatch
):
    with monkeypatch.context() as dying, pytest.raises(Killed):
        _die_after_view(dying, 1)
        _init("--src", str(raw))

    one = runner.invoke(app, ["status", "--dataset", "mimic-iv"])
    every = runner.invoke(app, ["status", "--all"])

    assert one.exit_code == 0
    assert "INCOMPLETE" in one.stdout
    assert "m4 init mimic-iv" in one.stdout
    assert every.exit_code == 0
    assert "Incomplete" in every.stdout


def test_init_download_fetches_what_an_interrupted_download_left_out(
    data_dir, monkeypatch
):
    """Some raw files in M4's own folder do not mean the download finished.
    Asked to download again, M4 must fetch the rest instead of preparing a
    dataset from the files that happened to arrive."""
    listing = "https://physionet.org/files/mimic-iv-demo/2.2/"
    files = {name: gzip.compress(text.encode()) for name, text in TABLES.items()}
    arrived = data_dir / "raw_files" / "mimic-iv-demo" / "hosp" / "admissions.csv.gz"
    arrived.parent.mkdir(parents=True)
    arrived.write_bytes(files["hosp/admissions"])

    class Response:
        def __init__(self, content=b"", headers=None):
            self.content = content
            self.status_code = 200
            self.headers = headers or {}
            self.reason = "OK"

        def iter_content(self, chunk_size=8192):
            yield self.content

    class Session:
        """Answers like the PhysioNet file listing, without any network."""

        def __init__(self):
            self.headers = {}
            self.auth = None

        def head(self, url, **kwargs):
            size = len(files[url.removeprefix(listing).removesuffix(".csv.gz")])
            return Response(headers={"content-length": str(size)})

        def get(self, url, **kwargs):
            asked = url.removeprefix(listing)
            if asked in ("hosp/", "icu/"):
                links = [
                    f'<a href="{name.split("/")[1]}.csv.gz">table</a>'
                    for name in files
                    if name.startswith(asked)
                ]
                return Response("".join(links).encode())
            return Response(files[asked.removesuffix(".csv.gz")])

    monkeypatch.setattr("m4.data_io.requests.Session", Session)

    result = runner.invoke(
        app,
        [
            "init",
            "mimic-iv-demo",
            "--download",
            "--no-interactive",
            "--json",
            "--events",
            "ndjson",
        ],
    )

    assert result.exit_code == 0
    events = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    skipped = [e for e in events if e["event"] == "download_file_skipped"]
    fetched = [e for e in events if e["event"] == "download_file_completed"]
    assert [Path(e["path"]).name for e in skipped] == ["admissions.csv.gz"]
    assert sorted(Path(e["path"]).name for e in fetched) == [
        "chartevents.csv.gz",
        "patients.csv.gz",
    ]
    assert events[-1]["result"]["prepared"] is True
    assert _views(data_dir, "mimic-iv-demo") == ALL_VIEWS
    _assert_ready(_listed("mimic-iv-demo"))
