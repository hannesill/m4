"""A dataset is reported ready only when its preparation ran to the end.

These tests run the commands a wrapper drives (`m4 init --json --events ndjson`
and `m4 list-datasets --json`) against a throwaway data directory and a few
rows of made-up CSV.gz data. "Killed" stands in for the process dying, which a
wrapper causes when its user cancels, and which leaves no chance to clean up.
"""

import errno
import gzip
import json
import os
import shutil
from pathlib import Path

import duckdb
import pytest
import requests
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
    assert len(list(in_flight.parent.glob("chartevents.parquet.*.part"))) == 1
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


# ------------------------------------------------------------
# Downloads that did not finish
# ------------------------------------------------------------

DEMO_LISTING = "https://physionet.org/files/mimic-iv-demo/2.2/"
FULL_LISTING = "https://physionet.org/files/mimiciv/3.1/"
SESSION = "m4.data_io.requests.Session"
# Made up. It only ever reaches the fake below.
FAKE_LOGIN = json.dumps({"username": "fake-user", "password": "FAKE-not-a-password"})

# Two tables in each folder, so that a download killed at the last one leaves
# both folders with files: nothing but M4's own note says it did not finish.
DOWNLOADED = {**TABLES, "icu/icustays": "subject_id,stay_id\n1,10\n2,20\n"}
DOWNLOADED_VIEWS = ALL_VIEWS | {"mimiciv_icu.icustays"}
LAST = "icu/icustays"


class _Answer:
    def __init__(self, content=b"", headers=None, dies=False):
        self.content = content
        self.status_code = 200
        self.headers = headers or {}
        self.reason = "OK"
        self._dies = dies

    def iter_content(self, chunk_size=8192):
        if self._dies:
            # Half of the file arrived when the process died.
            yield self.content[: len(self.content) // 2]
            raise Killed()
        yield self.content


class FakePhysioNet:
    """Stands in for requests.Session and answers like PhysioNet's listing of
    one dataset, without any network. Downloading `dies_at` kills the process."""

    def __init__(self, listing, tables=None, dies_at=None):
        self.listing = listing
        self.files = {
            name: gzip.compress(text.encode())
            for name, text in (tables or DOWNLOADED).items()
        }
        self.dies_at = dies_at
        self.headers = {}
        self.auth = None

    def __call__(self):
        return self

    def head(self, url, **kwargs):
        name = url.removeprefix(self.listing).removesuffix(".csv.gz")
        return _Answer(headers={"content-length": str(len(self.files[name]))})

    def get(self, url, **kwargs):
        asked = url.removeprefix(self.listing)
        if asked.endswith("/"):
            links = [
                f'<a href="{name.split("/")[1]}.csv.gz">table</a>'
                for name in self.files
                if name.startswith(asked)
            ]
            return _Answer("".join(links).encode())
        name = asked.removesuffix(".csv.gz")
        return _Answer(self.files[name], dies=name == self.dies_at)


def _run(*args: str, input: str | None = None):
    """Run an M4 command as a wrapper does and return (result, events)."""
    result = runner.invoke(app, [*args, "--json", "--events", "ndjson"], input=input)
    events = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    return result, events


def _raw_root(data_dir: Path, name: str = "mimic-iv") -> Path:
    return data_dir / "raw_files" / name


def _raw_files(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*.csv.gz"))


def _files_holding(root: Path, secret: str) -> list[str]:
    """The files under `root` that contain `secret`."""
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and secret.encode() in path.read_bytes()
    )


def _fetched(events: list[dict]) -> list[str]:
    return sorted(
        Path(e["path"]).name for e in events if e["event"] == "download_file_completed"
    )


def test_init_killed_while_downloading_fetches_the_rest_when_it_runs_again(
    data_dir, monkeypatch
):
    """`m4 init` downloads an open dataset itself. Killed while it does, the
    next run must not make a dataset of the files that happened to arrive."""
    with monkeypatch.context() as dying, pytest.raises(Killed):
        dying.setattr(SESSION, FakePhysioNet(DEMO_LISTING, dies_at=LAST))
        _run("init", "mimic-iv-demo", "--no-interactive")

    raw_root = _raw_root(data_dir, "mimic-iv-demo")
    assert _raw_files(raw_root) == [
        "hosp/admissions.csv.gz",
        "hosp/patients.csv.gz",
        "icu/chartevents.csv.gz",
    ]
    assert (raw_root / "icu" / "icustays.csv.gz.part").exists()
    _assert_not_ready(_listed("mimic-iv-demo"))

    monkeypatch.setattr(SESSION, FakePhysioNet(DEMO_LISTING))
    result, events = _run("init", "mimic-iv-demo", "--no-interactive")

    assert result.exit_code == 0
    assert _fetched(events) == ["icustays.csv.gz"]
    assert events[-1]["result"]["prepared"] is True
    assert _views(data_dir, "mimic-iv-demo") == DOWNLOADED_VIEWS
    _assert_ready(_listed("mimic-iv-demo"))


def test_download_killed_then_init_fetches_the_rest(data_dir, monkeypatch):
    with monkeypatch.context() as dying, pytest.raises(Killed):
        dying.setattr(SESSION, FakePhysioNet(DEMO_LISTING, dies_at=LAST))
        _run("download", "mimic-iv-demo")

    monkeypatch.setattr(SESSION, FakePhysioNet(DEMO_LISTING))
    result, events = _run("init", "mimic-iv-demo", "--no-interactive")

    assert result.exit_code == 0
    assert _fetched(events) == ["icustays.csv.gz"]
    assert _views(data_dir, "mimic-iv-demo") == DOWNLOADED_VIEWS
    _assert_ready(_listed("mimic-iv-demo"))


def test_download_killed_then_init_without_json_fetches_the_rest(data_dir, monkeypatch):
    monkeypatch.setattr("m4.config._find_project_root_from_cwd", Path.cwd)
    with monkeypatch.context() as dying, pytest.raises(Killed):
        dying.setattr(SESSION, FakePhysioNet(DEMO_LISTING, dies_at=LAST))
        runner.invoke(app, ["init", "mimic-iv-demo"])

    monkeypatch.setattr(SESSION, FakePhysioNet(DEMO_LISTING))
    result = runner.invoke(app, ["init", "mimic-iv-demo"])

    assert result.exit_code == 0
    assert _views(data_dir, "mimic-iv-demo") == DOWNLOADED_VIEWS
    _assert_ready(_listed("mimic-iv-demo"))


def test_download_that_cannot_be_finished_without_json_fails_without_a_traceback(
    data_dir, monkeypatch
):
    monkeypatch.setattr("m4.config._find_project_root_from_cwd", Path.cwd)
    with monkeypatch.context() as dying, pytest.raises(Killed):
        dying.setattr(SESSION, FakePhysioNet(DEMO_LISTING, dies_at=LAST))
        runner.invoke(app, ["init", "mimic-iv-demo"])

    class Offline(FakePhysioNet):
        def get(self, url, **kwargs):
            raise requests.exceptions.ConnectionError("no route to host")

    monkeypatch.setattr(SESSION, Offline(DEMO_LISTING))
    result = runner.invoke(app, ["init", "mimic-iv-demo"])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "Download failed" in result.output
    assert not list(data_dir.rglob("*.parquet"))
    _assert_not_ready(_listed("mimic-iv-demo"))


def test_credentialed_download_killed_is_only_finished_with_the_login(
    data_dir, monkeypatch
):
    with monkeypatch.context() as dying, pytest.raises(Killed):
        dying.setattr(SESSION, FakePhysioNet(FULL_LISTING, dies_at=LAST))
        _run("download", "mimic-iv", "--physionet-credentials-stdin", input=FAKE_LOGIN)

    # The note that the download left does not hold the login.
    assert (_raw_root(data_dir) / ".m4-downloading.json").exists()
    assert _files_holding(data_dir, "FAKE-not-a-password") == []

    # Without the login M4 cannot fetch the rest, and must not prepare a
    # dataset from the three tables that arrived.
    result, events = _init()

    assert result.exit_code == 1
    failure = events[-1]
    assert failure["event"] == "operation_failed"
    assert failure["error"]["code"] == "raw_files_missing"
    assert "did not finish" in failure["error"]["message"]
    assert not list(data_dir.rglob("*.parquet"))
    assert not _database(data_dir).exists()
    _assert_not_ready(_listed())

    monkeypatch.setattr(SESSION, FakePhysioNet(FULL_LISTING))
    result, events = _run(
        "init",
        "mimic-iv",
        "--no-interactive",
        "--download",
        "--physionet-credentials-stdin",
        input=FAKE_LOGIN,
    )

    assert result.exit_code == 0
    assert _fetched(events) == ["icustays.csv.gz"]
    assert events[-1]["result"]["prepared"] is True
    assert _views(data_dir) == DOWNLOADED_VIEWS
    _assert_ready(_listed())
    assert "FAKE-not-a-password" not in result.output
    assert _files_holding(data_dir, "FAKE-not-a-password") == []


def test_credentialed_download_killed_is_refused_without_json_too(
    data_dir, monkeypatch
):
    monkeypatch.setattr("m4.config._find_project_root_from_cwd", Path.cwd)
    with monkeypatch.context() as dying, pytest.raises(Killed):
        dying.setattr(SESSION, FakePhysioNet(FULL_LISTING, dies_at=LAST))
        _run("download", "mimic-iv", "--physionet-credentials-stdin", input=FAKE_LOGIN)

    result = runner.invoke(app, ["init", "mimic-iv"])

    assert result.exit_code == 1
    assert "Cannot Initialize" in result.output
    assert "m4 download mimic-iv" in result.output
    assert not list(data_dir.rglob("*.parquet"))
    _assert_not_ready(_listed())


def test_src_folder_with_an_unfinished_download_is_refused(
    data_dir, tmp_path, monkeypatch
):
    target = tmp_path / "my-download"
    with monkeypatch.context() as dying, pytest.raises(Killed):
        dying.setattr(SESSION, FakePhysioNet(DEMO_LISTING, dies_at=LAST))
        _run("download", "mimic-iv-demo", "--target", str(target))

    result, events = _run(
        "init", "mimic-iv-demo", "--src", str(target), "--no-interactive"
    )

    assert result.exit_code == 1
    failure = events[-1]
    assert failure["event"] == "operation_failed"
    assert failure["error"]["code"] == "raw_files_missing"
    assert f"m4 download mimic-iv-demo --target {target}" in failure["error"]["hint"]
    assert not list(data_dir.rglob("*.parquet"))
    _assert_not_ready(_listed("mimic-iv-demo"))
    # M4's check of a raw folder, which a wrapper asks before it starts, agrees.
    plan = runner.invoke(
        app,
        [
            "download",
            "mimic-iv-demo",
            "--target",
            str(target),
            "--command-only",
            "--json",
        ],
    )
    layout = json.loads(plan.stdout)["layout"]
    assert layout["ok"] is False
    assert "partial_download" in layout["warnings"]

    # Finishing the download as the hint says makes the folder a whole dataset.
    monkeypatch.setattr(SESSION, FakePhysioNet(DEMO_LISTING))
    assert _run("download", "mimic-iv-demo", "--target", str(target))[0].exit_code == 0
    result, events = _run(
        "init", "mimic-iv-demo", "--src", str(target), "--no-interactive"
    )

    assert result.exit_code == 0
    assert _views(data_dir, "mimic-iv-demo") == DOWNLOADED_VIEWS
    _assert_ready(_listed("mimic-iv-demo"))


def test_download_killed_without_a_note_is_finished_like_any_other(
    data_dir, monkeypatch
):
    # M4 0.5.5 and earlier left no note. The file that was being written when
    # the download was killed still says that it did not finish.
    with monkeypatch.context() as dying, pytest.raises(Killed):
        dying.setattr(SESSION, FakePhysioNet(DEMO_LISTING, dies_at=LAST))
        _run("download", "mimic-iv-demo")
    raw_root = _raw_root(data_dir, "mimic-iv-demo")
    (raw_root / ".m4-downloading.json").unlink()
    assert (raw_root / "icu" / "icustays.csv.gz.part").exists()

    monkeypatch.setattr(SESSION, FakePhysioNet(DEMO_LISTING))
    result, events = _run("init", "mimic-iv-demo", "--no-interactive")

    assert result.exit_code == 0
    assert _fetched(events) == ["icustays.csv.gz"]
    assert _views(data_dir, "mimic-iv-demo") == DOWNLOADED_VIEWS
    _assert_ready(_listed("mimic-iv-demo"))


def test_src_folder_with_a_file_that_is_still_arriving_is_refused(data_dir, raw):
    # A browser, like M4, keeps a file under <name>.part until it has all of it.
    arriving = raw / "icu" / "icustays.csv.gz.part"
    arriving.write_bytes(b"half of it")
    # One that was left beside the finished file says nothing.
    (raw / "hosp" / "admissions.csv.gz.part").write_bytes(b"left over")

    result, events = _init("--src", str(raw))

    assert result.exit_code == 1
    failure = events[-1]
    assert failure["error"]["code"] == "raw_files_missing"
    assert "icu/icustays.csv.gz.part" in failure["error"]["message"]
    assert not list(data_dir.rglob("*.parquet"))
    _assert_not_ready(_listed())

    arriving.unlink()
    result, _ = _init("--src", str(raw))

    assert result.exit_code == 0
    assert _views(data_dir) == ALL_VIEWS
    _assert_ready(_listed())


def test_m4s_raw_folder_without_one_of_the_dataset_folders_is_refused(data_dir):
    # A download that stopped before it reached icu/ and left nothing that says
    # so: one that M4 did not make, or one that was killed between two files.
    own = _write_raw(
        _raw_root(data_dir, "mimic-iv-demo"),
        {name: text for name, text in TABLES.items() if name.startswith("hosp/")},
    )

    result, events = _run("init", "mimic-iv-demo", "--no-interactive")

    # Not fetched unasked: it is not known that M4 was downloading at all.
    assert result.exit_code == 1
    failure = events[-1]
    assert failure["event"] == "operation_failed"
    assert failure["error"]["code"] == "raw_files_missing"
    assert "icu/" in failure["error"]["message"]
    assert failure["error"]["hint"] == (
        "Fetch them with: m4 download mimic-iv-demo. If these files are all the "
        f"dataset is to hold, run: m4 init mimic-iv-demo --src {own}"
    )
    assert not list(data_dir.rglob("*.parquet"))
    assert not _database(data_dir, "mimic-iv-demo").exists()
    _assert_not_ready(_listed("mimic-iv-demo"))


def test_folder_named_with_src_is_taken_as_it_is(data_dir):
    # Whoever means a dataset to hold only part of it says so with --src, for
    # M4's own raw folder as for any other.
    own = _write_raw(
        _raw_root(data_dir),
        {name: text for name, text in TABLES.items() if name.startswith("hosp/")},
    )
    assert _init()[0].exit_code == 1

    result, events = _init("--src", str(own))

    assert result.exit_code == 0
    assert events[-1]["result"]["prepared"] is True
    assert _views(data_dir) == {"mimiciv_hosp.admissions", "mimiciv_hosp.patients"}
    _assert_ready(_listed())


def test_folder_that_is_already_converted_need_not_be_among_the_raw_files(
    data_dir, raw
):
    # Raw files may be deleted once they are converted. What is left of them
    # still initializes a dataset whose other folder already has its tables.
    _init("--src", str(raw))
    shutil.rmtree(raw / "icu")

    result, _ = _init("--src", str(raw), "--force")

    assert result.exit_code == 0
    assert _views(data_dir) == ALL_VIEWS
    _assert_ready(_listed())


# ------------------------------------------------------------
# A conversion that did not finish, and another raw folder
# ------------------------------------------------------------


def test_conversion_that_failed_is_finished_from_the_same_folder_without_the_bad_file(
    data_dir, raw
):
    # What macOS leaves beside a file on a drive that cannot keep its attributes.
    junk = raw / "hosp" / "._admissions.csv.gz"
    junk.write_bytes(b"\x00\x05\x16\x07 not a table")

    result, events = _init("--src", str(raw))

    assert result.exit_code == 1
    assert events[-1]["error"]["code"] == "conversion_failed"
    _assert_not_ready(_listed())

    junk.unlink()
    result, _ = _init("--src", str(raw))

    assert result.exit_code == 0
    assert _views(data_dir) == ALL_VIEWS
    _assert_ready(_listed())


def _converted(data_dir: Path) -> list[str]:
    parquet = _parquet(data_dir)
    return sorted(p.relative_to(parquet).as_posix() for p in parquet.rglob("*.parquet"))


@pytest.mark.parametrize("other_is_m4s_own_folder", [False, True])
@pytest.mark.parametrize("other_holds_a_new_table", [False, True])
def test_conversion_killed_then_init_from_another_folder_is_refused(
    data_dir,
    raw,
    tmp_path,
    monkeypatch,
    other_is_m4s_own_folder,
    other_holds_a_new_table,
):
    with monkeypatch.context() as dying, pytest.raises(Killed):
        _die_before_publishing(dying, "patients")
        _init("--src", str(raw))
    assert _converted(data_dir) == [
        "hosp/admissions.parquet",
        "icu/chartevents.parquet",
    ]

    # Another folder holds the raw files of the tables that were converted,
    # and not the one of the table that was in flight.
    tables = {name: text for name, text in TABLES.items() if name != "hosp/patients"}
    if other_holds_a_new_table:
        tables["hosp/transfers"] = "subject_id,hadm_id\n1,100\n"
    other = _raw_root(data_dir) if other_is_m4s_own_folder else tmp_path / "other"
    _write_raw(other, tables)

    result, events = _init() if other_is_m4s_own_folder else _init("--src", str(other))

    # Building the database now would hide that patients is missing.
    assert result.exit_code == 1
    failure = events[-1]
    assert failure["event"] == "operation_failed"
    assert failure["error"]["code"] == "raw_files_missing"
    assert "hosp/patients" in failure["error"]["message"]
    assert str(raw) in failure["error"]["hint"]
    assert _converted(data_dir) == [
        "hosp/admissions.parquet",
        "icu/chartevents.parquet",
    ]
    assert not _database(data_dir).exists()
    _assert_not_ready(_listed())

    result, _ = _init("--src", str(raw))

    assert result.exit_code == 0
    assert _views(data_dir) == ALL_VIEWS


# ------------------------------------------------------------
# What status goes by
# ------------------------------------------------------------


@pytest.mark.parametrize("made_from_m4s_own_folder", [True, False])
def test_raw_files_added_after_init_are_not_ready_until_init_runs_again(
    data_dir, raw, made_from_m4s_own_folder
):
    own = _raw_root(data_dir)
    if made_from_m4s_own_folder:
        shutil.copytree(raw, own)
        assert _init()[0].exit_code == 0
    else:
        assert _init("--src", str(raw))[0].exit_code == 0
    _assert_ready(_listed())

    # A download that went on, or a copy by hand, brings the raw file of a
    # table the dataset does not have.
    _write_raw(own, {"icu/icustays": "subject_id,stay_id\n1,10\n"})

    listed = _listed()
    assert listed["prepared"] is False
    assert listed["setup_state"] == "incomplete"

    result, events = _init()

    assert result.exit_code == 0
    converted = [e for e in events if e["event"] == "conversion_file_completed"]
    assert [Path(e["path"]).name for e in converted] == ["icustays.parquet"]
    assert _views(data_dir) == ALL_VIEWS | {"mimiciv_icu.icustays"}
    _assert_ready(_listed())


def test_init_from_another_folder_does_not_vouch_for_m4s_own_raw_files(data_dir, raw):
    assert _init("--src", str(raw))[0].exit_code == 0
    _write_raw(_raw_root(data_dir), {"icu/icustays": "subject_id,stay_id\n1,10\n"})
    assert _listed()["setup_state"] == "incomplete"

    # The folder the dataset was made from knows nothing of the new file.
    result, events = _init("--src", str(raw))

    assert result.exit_code == 0
    assert events[-1]["result"]["prepared"] is False
    assert _views(data_dir) == ALL_VIEWS
    assert _listed()["setup_state"] == "incomplete"

    result, events = _init()

    assert result.exit_code == 0
    assert events[-1]["result"]["prepared"] is True
    assert _views(data_dir) == ALL_VIEWS | {"mimiciv_icu.icustays"}
    _assert_ready(_listed())


def test_raw_file_that_arrives_while_init_runs_is_not_vouched_for(
    data_dir, monkeypatch
):
    # A download that M4 does not make, such as wget, may still be running
    # when `m4 init` starts. What it brings after the conversion was decided
    # has no table, and the run that just ended must not vouch for it.
    own = _write_raw(_raw_root(data_dir))
    real_emit = NdjsonEventReporter.emit

    def emit(self, event, **fields):
        real_emit(self, event, **fields)
        if event == "conversion_completed":
            _write_raw(own, {"icu/icustays": "subject_id,stay_id\n1,10\n"})

    with monkeypatch.context() as downloading:
        downloading.setattr(NdjsonEventReporter, "emit", emit)
        result, events = _init()

    assert result.exit_code == 0
    assert events[-1]["result"]["prepared"] is False
    assert _listed()["setup_state"] == "incomplete"

    result, events = _init()

    assert result.exit_code == 0
    assert events[-1]["result"]["prepared"] is True
    assert _views(data_dir) == ALL_VIEWS | {"mimiciv_icu.icustays"}
    _assert_ready(_listed())


def test_dataset_made_from_a_folder_is_ready_beside_a_download_that_was_cut_short(
    data_dir, raw, monkeypatch
):
    # Someone gives up on a download and brings the files another way. What
    # the download left in M4's own raw folder is no reason to hold back the
    # dataset made from the folder they chose.
    with monkeypatch.context() as dying, pytest.raises(Killed):
        dying.setattr(SESSION, FakePhysioNet(FULL_LISTING, dies_at=LAST))
        _run("download", "mimic-iv", "--physionet-credentials-stdin", input=FAKE_LOGIN)

    result, events = _init("--src", str(raw))

    assert result.exit_code == 0
    assert events[-1]["result"]["prepared"] is True
    assert _views(data_dir) == ALL_VIEWS
    _assert_ready(_listed())

    # The download is finished after all, and brings a table the folder lacked.
    monkeypatch.setattr(SESSION, FakePhysioNet(FULL_LISTING))
    result, _ = _run(
        "download", "mimic-iv", "--physionet-credentials-stdin", input=FAKE_LOGIN
    )

    assert result.exit_code == 0
    assert _listed()["setup_state"] == "incomplete"

    result, _ = _init()

    assert result.exit_code == 0
    assert _views(data_dir) == DOWNLOADED_VIEWS
    _assert_ready(_listed())


def test_download_again_leaves_a_ready_dataset_ready(data_dir, monkeypatch):
    monkeypatch.setattr(SESSION, FakePhysioNet(DEMO_LISTING))
    assert _run("init", "mimic-iv-demo", "--no-interactive")[0].exit_code == 0
    _assert_ready(_listed("mimic-iv-demo"))

    result, events = _run("download", "mimic-iv-demo")

    # Every file is complete, so nothing is fetched and nothing is noted.
    assert result.exit_code == 0
    assert _fetched(events) == []
    assert not (_raw_root(data_dir, "mimic-iv-demo") / ".m4-downloading.json").exists()
    _assert_ready(_listed("mimic-iv-demo"))


def test_wget_tree_in_m4s_own_raw_folder_is_ready_once_init_ran_on_the_folder_named(
    data_dir,
):
    # Plain `wget -r` into M4's raw folder. The files M4 sees there afterwards
    # are the ones the dataset was made from, deeper down as they lie.
    nested = _write_raw(
        _raw_root(data_dir) / "physionet.org" / "files" / "mimiciv" / "3.1"
    )

    result, events = _init()

    assert result.exit_code == 1
    assert events[-1]["error"]["hint"] == f"Run: m4 init mimic-iv --src {nested}"

    result, events = _init("--src", str(nested))

    assert result.exit_code == 0
    assert events[-1]["result"]["prepared"] is True
    _assert_ready(_listed())


def test_raw_files_removed_after_init_leave_the_dataset_ready(data_dir):
    # Raw files are often deleted once they are converted, to get the disk back.
    own = _write_raw(_raw_root(data_dir))
    _init()

    shutil.rmtree(own / "icu")
    _assert_ready(_listed())

    shutil.rmtree(own)
    _assert_ready(_listed())


def test_database_reached_through_a_symlink_is_ready_after_init(
    data_dir, raw, tmp_path
):
    # The database is kept on another disk, with a link where M4 looks for it.
    other_disk = tmp_path / "other-disk"
    other_disk.mkdir()
    _database(data_dir).parent.mkdir(parents=True)
    _database(data_dir).symlink_to(other_disk / "mimic_iv.duckdb")

    result, events = _init("--src", str(raw))

    assert result.exit_code == 0
    assert events[-1]["result"]["prepared"] is True
    assert (other_disk / "mimic_iv.duckdb").is_file()
    _assert_ready(_listed())


def test_init_into_another_database_says_prepared_as_status_does(
    data_dir, raw, tmp_path
):
    # M4 reads a dataset from its default database, which this run did not make.
    result, events = _init("--src", str(raw), "--db-path", str(tmp_path / "my.duckdb"))

    assert result.exit_code == 0
    assert (tmp_path / "my.duckdb").exists()
    listed = _listed()
    assert listed["setup_state"] == "missing_database"
    assert events[-1]["result"]["prepared"] is listed["prepared"] is False

    result, events = _init("--src", str(raw))

    assert result.exit_code == 0
    assert events[-1]["result"]["prepared"] is True
    _assert_ready(_listed())


# ------------------------------------------------------------
# Which folder M4 names when the files sit deeper
# ------------------------------------------------------------


def _wget_tree_with_several_datasets(root: Path) -> dict[str, Path]:
    files = root / "physionet.org" / "files"
    return {
        "mimic-iv": _write_raw(files / "mimiciv" / "3.1"),
        "mimic-iv-note": _write_raw(
            files / "mimic-iv-note" / "2.2",
            {"note/discharge": "subject_id,text\n1,home\n"},
        ),
        "eicu": _write_raw(
            files / "eicu-crd" / "2.0", {"patient": "patientunitstayid\n1\n"}
        ),
    }


def test_wget_tree_with_other_datasets_names_the_folder_of_the_notes(
    data_dir, tmp_path
):
    tree = tmp_path / "downloads"
    folders = _wget_tree_with_several_datasets(tree)

    result, events = _run(
        "init", "mimic-iv-note", "--src", str(tree), "--no-interactive"
    )

    # Not hosp/, which holds more files and would fill the notes with MIMIC-IV.
    assert result.exit_code == 1
    assert events[-1]["error"]["code"] == "raw_files_missing"
    assert events[-1]["error"]["hint"] == f"Choose {folders['mimic-iv-note']} instead."

    result, _ = _run(
        "init",
        "mimic-iv-note",
        "--src",
        str(folders["mimic-iv-note"]),
        "--no-interactive",
    )

    assert result.exit_code == 0
    assert _views(data_dir, "mimic-iv-note") == {"mimiciv_note.discharge"}


def test_dataset_with_its_tables_directly_in_its_folder(data_dir, tmp_path):
    # eICU has no folders of its own, in a folder M4 is pointed at and in M4's.
    eicu = {"patient": "patientunitstayid\n1\n2\n", "lab": "patientunitstayid\n1\n"}
    views = {"eicu_crd.patient", "eicu_crd.lab"}
    chosen = _write_raw(tmp_path / "eicu-crd" / "2.0", eicu)

    result, events = _run("init", "eicu", "--src", str(chosen), "--no-interactive")

    assert result.exit_code == 0
    assert events[-1]["result"]["prepared"] is True
    assert _views(data_dir, "eicu") == views
    _assert_ready(_listed("eicu"))

    _write_raw(_raw_root(data_dir, "eicu"), {**eicu, "vitalperiodic": "a\n1\n"})
    assert _listed("eicu")["setup_state"] == "incomplete"

    result, _ = _run("init", "eicu", "--no-interactive")

    assert result.exit_code == 0
    assert _views(data_dir, "eicu") == views | {"eicu_crd.vitalperiodic"}
    _assert_ready(_listed("eicu"))


def test_wget_tree_where_several_folders_fit_names_them_all(data_dir, tmp_path):
    # eICU keeps its tables directly in its folder, like every folder that
    # holds another dataset's files. M4 cannot tell which one is meant.
    tree = tmp_path / "downloads"
    folders = _wget_tree_with_several_datasets(tree)

    result, events = _run("init", "eicu", "--src", str(tree), "--no-interactive")

    assert result.exit_code == 1
    failure = events[-1]
    assert failure["error"]["code"] == "raw_files_missing"
    assert str(folders["eicu"]) in failure["error"]["hint"]
    assert "instead" not in failure["error"]["hint"]
    assert not list(data_dir.rglob("*.parquet"))
    _assert_not_ready(_listed("eicu"))


# ------------------------------------------------------------
# A disk that is full
# ------------------------------------------------------------

PREPARED_MARKER = "mimic_iv.duckdb.m4-prepared.json"
CONVERSION_NOTE = ".m4-converting.json"


def _disk_full_when_writing(monkeypatch, name: str) -> None:
    """Fail as a full disk does when M4 writes the file called `name`."""
    real_write_text = Path.write_text

    def write_text(self, *args, **kwargs):
        if self.name.startswith(name):
            raise OSError(errno.ENOSPC, "No space left on device", str(self))
        return real_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", write_text)


@pytest.mark.parametrize(
    ("file_name", "code"),
    [(CONVERSION_NOTE, "conversion_failed"), (PREPARED_MARKER, "duckdb_init_failed")],
)
def test_full_disk_is_a_reported_failure(data_dir, raw, monkeypatch, file_name, code):
    with monkeypatch.context() as full:
        _disk_full_when_writing(full, file_name)
        result, events = _init("--src", str(raw))

    # A wrapper learns of the failure from the last event, not from a traceback.
    assert result.exit_code == 1
    failure = events[-1]
    assert failure["event"] == "operation_failed"
    assert failure["error"]["code"] == code
    _assert_not_ready(_listed())

    result, _ = _init("--src", str(raw))

    assert result.exit_code == 0
    _assert_ready(_listed())


@pytest.mark.parametrize("file_name", [CONVERSION_NOTE, PREPARED_MARKER])
def test_full_disk_is_a_reported_failure_without_json_too(
    data_dir, raw, monkeypatch, file_name
):
    monkeypatch.setattr("m4.config._find_project_root_from_cwd", Path.cwd)

    with monkeypatch.context() as full:
        _disk_full_when_writing(full, file_name)
        result = runner.invoke(
            app, ["init", "mimic-iv", "--src", str(raw)], input="n\n"
        )

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "Materialize derived tables?" not in result.output
    _assert_not_ready(_listed())
