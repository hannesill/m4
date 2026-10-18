"""m4 fetch-images: a cohort's images from PhysioNet, resumably, never the whole dataset."""

import json
import threading
from pathlib import Path

import duckdb
import pandas as pd
import pytest
import requests
from typer.testing import CliRunner

import m4
import m4.config as cfg_mod
from m4.cli import app
from m4.core.datasets import DatasetRegistry
from m4.data_io import PHYSIONET_LOGIN_USER_AGENT, PhysioNetCredentials
from m4.services.events import EventReporter
from m4.services.fetch_images import _fetch_image, fetch_images_service
from m4.services.results import CommandError, CommandResult

LISTING = "https://physionet.org/files/mimic-cxr-jpg/2.1.0/"
A = "files/p10/p10000032/s50414267/02aa804e-bde0afdd.jpg"
B = "files/p10/p10000764/s57375967/174413ec-4ec4c1f7.jpg"
IMAGES = {A: b"A" * 100, B: b"B" * 70}
LOGIN = PhysioNetCredentials(username="alice", password="s3cret-pw")


class Response:
    def __init__(self, status_code=200, body=b"", headers=None):
        self.status_code = status_code
        self.body = body
        self.headers = headers or {}
        self.reason = "Reason"

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def iter_content(self, chunk_size=1):
        for index in range(0, len(self.body), chunk_size):
            yield self.body[index : index + chunk_size]


class PhysioNet:
    """Serves IMAGES as PhysioNet does, Range requests included.

    `script[path]` lists what to answer the first requests for an image with
    instead: a Response, or an exception to raise.
    """

    def __init__(self, images=IMAGES):
        self.images = images
        self.script: dict[str, list] = {}
        # Image path -> bytes after which each connection breaks
        self.cut: dict[str, int] = {}
        self.requests: list[dict] = []

    def get(self, session, url, headers):
        path = url.removeprefix(LISTING)
        self.requests.append(
            {
                "path": path,
                "range": headers.get("Range"),
                "user_agent": session.headers.get("User-Agent"),
                "auth": session.auth,
            }
        )
        if self.script.get(path):
            answer = self.script[path].pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer
        if path not in self.images:
            return Response(404)
        body = self.images[path]
        if headers.get("Range"):
            start = int(headers["Range"].removeprefix("bytes=").removesuffix("-"))
            status, sent = 206, body[start:]
            sent_headers = {
                "content-range": f"bytes {start}-{len(body) - 1}/{len(body)}"
            }
        else:
            status, sent = 200, body
            sent_headers = {"content-length": str(len(body))}
        if path in self.cut and len(sent) > self.cut[path]:
            return Broken(sent, self.cut[path], status, sent_headers)
        return Response(status, sent, sent_headers)


@pytest.fixture
def physionet(monkeypatch):
    server = PhysioNet()

    class Session:
        def __init__(self):
            self.headers = {}
            self.auth = None

        def get(self, url, stream=False, timeout=None, headers=None):
            # What _PhysioNetAuth does for a real request
            if self.auth is not None:
                self.auth(requests.Request("GET", url).prepare())
            return server.get(self, url, headers or {})

        def close(self):
            pass

    monkeypatch.setattr("m4.data_io.requests.Session", Session)
    return server


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    root = tmp_path / "m4_data"
    monkeypatch.setattr(cfg_mod, "_PROJECT_DATA_DIR", root)
    monkeypatch.setattr(cfg_mod, "_DEFAULT_DATABASES_DIR", root / "databases")
    monkeypatch.setattr(cfg_mod, "_DEFAULT_PARQUET_DIR", root / "parquet")
    monkeypatch.setattr(cfg_mod, "_CUSTOM_DATASETS_DIR", root / "datasets")
    return root


def fetch(frame, **kwargs):
    kwargs.setdefault("physionet_credentials", LOGIN)
    kwargs.setdefault("backoff_seconds", 0)
    return fetch_images_service("mimic-cxr-jpg", frame, **kwargs)


def paths(*items):
    return pd.DataFrame({"image_path": list(items)})


def test_images_land_at_their_path_below_the_raw_folder(physionet, data_dir):
    result = fetch(paths(A, B, A))

    assert isinstance(result, CommandResult)
    root = data_dir / "raw_files" / "mimic-cxr-jpg"
    assert result.data["root"] == str(root)
    assert (result.data["fetched"], result.data["skipped"]) == (2, 0)
    assert result.data["bytes_downloaded"] == 170
    assert (root / A).read_bytes() == IMAGES[A]
    assert (root / B).read_bytes() == IMAGES[B]
    # Each image once, with the login, as PhysioNet reads it
    assert sorted(r["path"] for r in physionet.requests) == [A, B]
    assert {r["user_agent"] for r in physionet.requests} == {PHYSIONET_LOGIN_USER_AGENT}


def test_images_that_are_there_are_not_fetched_again(physionet, tmp_path):
    (tmp_path / A).parent.mkdir(parents=True)
    (tmp_path / A).write_bytes(IMAGES[A])

    result = fetch(paths(A, B), target=str(tmp_path))

    assert (result.data["fetched"], result.data["skipped"]) == (1, 1)
    assert [r["path"] for r in physionet.requests] == [B]


def test_a_part_file_is_resumed_where_it_stopped(physionet, tmp_path):
    part = tmp_path / (A + ".part")
    part.parent.mkdir(parents=True)
    part.write_bytes(IMAGES[A][:40])

    result = fetch(paths(A), target=str(tmp_path))

    assert result.ok
    assert physionet.requests[0]["range"] == "bytes=40-"
    assert (tmp_path / A).read_bytes() == IMAGES[A]
    assert not part.exists()


def test_a_part_file_that_holds_every_byte_is_finished(physionet, tmp_path):
    part = tmp_path / (A + ".part")
    part.parent.mkdir(parents=True)
    part.write_bytes(IMAGES[A])
    physionet.script[A] = [Response(416, headers={"content-range": "bytes */100"})]

    assert fetch(paths(A), target=str(tmp_path)).ok
    assert (tmp_path / A).read_bytes() == IMAGES[A]


def test_stalls_and_bad_gateways_are_retried_and_resumed(physionet, tmp_path):
    physionet.script[A] = [
        Response(502),
        requests.exceptions.ConnectionError("reset"),
        requests.exceptions.ConnectionError("refused"),
        # The connection closes after 30 bytes of the image
        Response(200, IMAGES[A][:30], {"content-length": "100"}),
    ]

    result = fetch(paths(A), target=str(tmp_path))

    assert result.ok
    assert (tmp_path / A).read_bytes() == IMAGES[A]
    assert [r["range"] for r in physionet.requests] == [None] * 4 + ["bytes=30-"]


class Broken(Response):
    """Delivers `delivered` bytes, then the connection breaks.

    As urllib3 does, it hands over whole pieces of `chunk_size` only, and
    what it read of the last piece is lost with the connection.
    """

    def __init__(self, body, delivered, status_code=200, headers=None):
        super().__init__(
            status_code, body, headers or {"content-length": str(len(body))}
        )
        self.delivered = delivered

    def iter_content(self, chunk_size=1):
        whole = self.delivered // chunk_size * chunk_size
        for index in range(0, whole, chunk_size):
            yield self.body[index : index + chunk_size]
        raise requests.exceptions.ChunkedEncodingError("IncompleteRead")


def test_a_broken_connection_keeps_what_it_delivered(physionet, tmp_path):
    """At PhysioNet's slowest, connections break every few tens of KB."""
    image = bytes(range(256)) * 400  # 100 KB
    physionet.images = {**IMAGES, A: image}
    physionet.script[A] = [Broken(image, 50_000)]

    result = fetch(paths(A), target=str(tmp_path))

    assert result.ok
    assert (tmp_path / A).read_bytes() == image
    # The retry went on from the whole pieces of the 50,000 bytes delivered
    assert [r["range"] for r in physionet.requests] == [None, "bytes=49152-"]


def test_the_pause_starts_over_after_an_attempt_that_brought_bytes(physionet, tmp_path):
    """Not a minute's pause before each of the dozens of resumes a slow day needs."""
    image = bytes(range(256)) * 400  # 100 KB
    physionet.images = {**IMAGES, A: image}
    physionet.script[A] = [Response(503), Response(503)]
    physionet.cut[A] = 20_000  # then every connection breaks after 20 KB
    pauses = []

    class Stop(threading.Event):
        def wait(self, timeout=None):
            pauses.append(timeout)
            return False

    outcome = _fetch_image(
        requests.Session(),
        LISTING + A,
        tmp_path / A,
        stop=Stop(),
        on_start=lambda there, size: None,
        on_bytes=lambda count: None,
        patience_seconds=600,
        backoff_seconds=5,
    )

    assert outcome == "fetched"
    assert (tmp_path / A).read_bytes() == image
    assert pauses[:2] == [5, 10]  # Nothing arrived: the pause grew
    assert len(pauses) > 4 and set(pauses[2:]) == {5}


def test_an_image_that_keeps_failing_is_reported_and_the_others_arrive(
    physionet, tmp_path
):
    physionet.script[A] = [Response(503)]

    # No patience: given up at the first failure that brought no byte
    result = fetch(paths(A, B), target=str(tmp_path), patience_seconds=0)

    assert isinstance(result, CommandError)
    assert result.code == "images_incomplete"
    assert result.data["fetched"] == 1
    assert [f["image_path"] for f in result.data["failed"]] == [A]
    assert result.data["failed"][0]["code"] == "download_network_failed"
    assert "Last error: HTTP 503" in result.data["failed"][0]["message"]
    assert (tmp_path / B).exists() and not (tmp_path / A).exists()


def test_an_image_physionet_does_not_have_is_not_retried(physionet, tmp_path):
    missing = "files/p10/p10000032/s50414267/missing.jpg"

    result = fetch(paths(missing, B), target=str(tmp_path))

    assert result.code == "images_incomplete"
    assert result.data["failed"] == [
        {
            "image_path": missing,
            "code": "image_not_found",
            "message": f"PhysioNet has no file at {LISTING}{missing}.",
        }
    ]
    assert [r["path"] for r in physionet.requests].count(missing) == 1


def test_access_refused_stops_the_run_and_names_the_agreement(physionet, tmp_path):
    """A MIMIC-IV login without the MIMIC-CXR-JPG DUA is refused."""
    physionet.script[A] = [Response(403)]
    physionet.script[B] = [Response(403)]

    result = fetch(paths(A, B), target=str(tmp_path), connections=1)

    assert isinstance(result, CommandError)
    assert result.code == "physionet_access_forbidden"
    assert "https://physionet.org/content/mimic-cxr-jpg/" in result.hint
    assert result.data["fetched"] == 0
    assert not list(tmp_path.rglob("*.jpg"))


def test_paths_that_are_not_the_datasets_images_are_refused(physionet, tmp_path):
    result = fetch(
        paths(A, "../../.ssh/id_rsa", "files/p10/x.jpg"), target=str(tmp_path)
    )

    assert result.code == "image_list_invalid"
    assert "../../.ssh/id_rsa" in result.message
    assert physionet.requests == []


def test_a_list_longer_than_the_limit_is_refused(physionet, tmp_path):
    result = fetch(paths(A, B), target=str(tmp_path), max_images=1)

    assert result.code == "too_many_images"
    assert physionet.requests == []


def test_images_that_are_all_there_need_no_login(physionet, tmp_path):
    for path in (A, B):
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_bytes(IMAGES[path])

    result = fetch(paths(A, B), target=str(tmp_path), physionet_credentials=None)

    assert result.ok
    assert (result.data["fetched"], result.data["skipped"]) == (0, 2)
    assert physionet.requests == []


def test_a_login_is_asked_for_before_anything_is_fetched(physionet, tmp_path):
    (tmp_path / A).parent.mkdir(parents=True)
    (tmp_path / A).write_bytes(IMAGES[A])

    result = fetch(paths(A, B), target=str(tmp_path), physionet_credentials=None)

    assert result.code == "missing_credentials"
    assert "1 of 2 images" in result.message
    assert (result.data["image_count"], result.data["skipped"]) == (2, 1)
    assert physionet.requests == []


def test_the_limit_counts_only_the_images_to_fetch(physionet, tmp_path):
    (tmp_path / A).parent.mkdir(parents=True)
    (tmp_path / A).write_bytes(IMAGES[A])

    assert fetch(paths(A, B), target=str(tmp_path), max_images=1).ok


class Recorder(EventReporter):
    def __init__(self):
        super().__init__(command="fetch-images", enabled=True)
        self.events: list[dict] = []
        self.seen = {name: threading.Event() for name in ("started", "progress")}

    def emit(self, event, **fields):
        self.events.append({"event": event, **fields})
        if event == "download_file_started":
            self.seen["started"].set()
        if event == "download_file_progress":
            self.seen["progress"].set()


def test_each_image_reports_its_bytes_as_m4_download_does(
    physionet, tmp_path, monkeypatch
):
    monkeypatch.setattr("m4.services.fetch_images.PROGRESS_SECONDS", 0.01)
    reporter = Recorder()

    class Slow(Response):
        """Sends the image in three pieces, each once the last was reported."""

        def iter_content(self, chunk_size=1):
            yield self.body[:10]
            reporter.seen["started"].wait(5)
            yield self.body[10:50]
            reporter.seen["progress"].wait(5)
            yield self.body[50:]

    physionet.script[A] = [Slow(200, IMAGES[A], {"content-length": "100"})]

    result = fetch(paths(A), target=str(tmp_path), event_reporter=reporter)

    assert result.ok
    of_a = [e for e in reporter.events if e.get("path") == str(tmp_path / A)]
    assert of_a[0]["event"] == "download_file_started"
    assert of_a[0]["url"] == LISTING + A
    assert of_a[0]["bytes_total"] == 100
    assert "download_file_progress" in [e["event"] for e in of_a]
    assert of_a[-1] == {
        "event": "download_file_completed",
        "path": str(tmp_path / A),
        "bytes_downloaded": 100,
        "bytes_total": 100,
    }


def test_local_image_paths_says_where_each_row_is_without_fetching(physionet, tmp_path):
    (tmp_path / A).parent.mkdir(parents=True)
    (tmp_path / A).write_bytes(IMAGES[A])
    cohort = pd.DataFrame({"label": [1, 0, 1], "image_path": [A, B, None]})

    located = m4.local_image_paths("mimic-cxr-jpg", cohort, target=tmp_path)

    assert list(located["label"]) == [1, 0, 1]
    assert list(located["local_path"]) == [str(tmp_path / A), str(tmp_path / B), None]
    assert list(located["present"]) == [True, False, False]
    assert physionet.requests == []
    with pytest.raises(m4.ImageFetchError) as caught:
        m4.local_image_paths("mimic-cxr-jpg", paths("elsewhere/x.jpg"))
    assert caught.value.code == "image_list_invalid"


def test_a_dataset_without_images_is_refused(physionet):
    result = fetch_images_service("mimic-iv-demo", paths(A))

    assert result.code == "not_an_imaging_dataset"


def test_ids_are_looked_up_in_the_images_view(physionet, tmp_path, monkeypatch):
    cxr = DatasetRegistry.get("mimic-cxr-jpg")
    db_path = tmp_path / "cxr.duckdb"
    con = duckdb.connect(str(db_path))
    con.execute("CREATE SCHEMA mimic_cxr")
    con.execute(
        "CREATE TABLE mimic_cxr.metadata AS SELECT * FROM (VALUES "
        "('02aa804e-bde0afdd', 10000032, 50414267), "
        "('174413ec-4ec4c1f7', 10000764, 57375967)"
        ") t(dicom_id, subject_id, study_id)"
    )
    con.execute(
        f"CREATE VIEW mimic_cxr.images AS SELECT *, {cxr.images.path_sql()} "
        "AS image_path FROM mimic_cxr.metadata"
    )
    con.close()
    monkeypatch.setenv("M4_DB_PATH", str(db_path))
    target = tmp_path / "raw"

    found = fetch(pd.DataFrame({"dicom_id": ["174413ec-4ec4c1f7"]}), target=str(target))
    unknown = fetch(pd.DataFrame({"dicom_id": ["nope"]}), target=str(target))

    assert found.ok and (target / B).read_bytes() == IMAGES[B]
    assert unknown.code == "image_list_invalid"
    assert "nope" in unknown.message


def test_paths_the_images_view_gives_are_checked_too(physionet, tmp_path, monkeypatch):
    """A custom dataset's table could hold any path."""
    db_path = tmp_path / "odd.duckdb"
    con = duckdb.connect(str(db_path))
    con.execute("CREATE SCHEMA mimic_cxr")
    con.execute(
        "CREATE VIEW mimic_cxr.images AS "
        "SELECT 'x' AS dicom_id, '../../outside.jpg' AS image_path"
    )
    con.close()
    monkeypatch.setenv("M4_DB_PATH", str(db_path))

    result = fetch(pd.DataFrame({"dicom_id": ["x"]}), target=str(tmp_path / "raw"))

    assert result.code == "image_list_invalid"
    assert physionet.requests == []


def test_ids_need_the_dataset_initialized(physionet, tmp_path, monkeypatch):
    monkeypatch.setenv("M4_DB_PATH", str(tmp_path / "absent.duckdb"))

    result = fetch(pd.DataFrame({"dicom_id": ["x"]}), target=str(tmp_path))

    assert result.code == "dataset_not_initialized"


def test_cli_reports_progress_as_ndjson_and_reads_the_login_from_stdin(
    physionet, tmp_path
):
    cohort = tmp_path / "cohort.csv"
    pd.DataFrame({"dicom_id": ["a", "b"], "path": [A, B]}).to_csv(cohort, index=False)
    target = tmp_path / "raw"

    result = CliRunner().invoke(
        app,
        [
            "fetch-images",
            "mimic-cxr-jpg",
            "--from-csv",
            str(cohort),
            "--target",
            str(target),
            "--json",
            "--events",
            "ndjson",
            "--physionet-credentials-stdin",
        ],
        input=json.dumps({"username": "alice", "password": "s3cret-pw"}),
    )

    assert result.exit_code == 0, result.stdout
    assert "s3cret-pw" not in result.stdout
    events = [json.loads(line) for line in result.stdout.splitlines()]
    names = [event["event"] for event in events]
    assert names[:2] == ["operation_started", "download_started"]
    assert events[1]["file_count"] == 2
    assert names.count("download_file_completed") == 2
    assert names[-2:] == ["download_completed", "operation_completed"]
    final = events[-1]["result"]
    assert (final["ok"], final["fetched"], final["root"]) == (True, 2, str(target))


def test_cli_without_json_prints_a_line_per_image(physionet, tmp_path):
    cohort = tmp_path / "cohort.csv"
    pd.DataFrame({"image_path": [A, B]}).to_csv(cohort, index=False)
    physionet.script[B] = [Response(404)]

    result = CliRunner().invoke(
        app,
        [
            "fetch-images",
            "mimic-cxr-jpg",
            "--from-csv",
            str(cohort),
            "--target",
            str(tmp_path / "raw"),
            "--physionet-credentials-stdin",
        ],
        input=json.dumps({"username": "alice", "password": "pw"}),
    )

    assert result.exit_code == 1
    output = " ".join(result.stdout.split())
    assert "/2] 02aa804e-bde0afdd.jpg" in output  # the image that arrived
    assert "/2] 174413ec-4ec4c1f7.jpg: image_not_found" in output


def test_cli_failure_event_carries_what_the_run_did(physionet, tmp_path):
    cohort = tmp_path / "cohort.csv"
    pd.DataFrame({"image_path": [A]}).to_csv(cohort, index=False)
    physionet.script[A] = [Response(403)]

    result = CliRunner().invoke(
        app,
        [
            "fetch-images",
            "mimic-cxr-jpg",
            "--from-csv",
            str(cohort),
            "--target",
            str(tmp_path / "raw"),
            "--json",
            "--events",
            "ndjson",
            "--physionet-credentials-stdin",
        ],
        input=json.dumps({"username": "alice", "password": "pw"}),
    )

    assert result.exit_code == 1
    failed = json.loads(result.stdout.splitlines()[-1])
    assert failed["event"] == "operation_failed"
    assert failed["error"]["code"] == "physionet_access_forbidden"
    assert failed["data"]["fetched"] == 0


def test_python_api_raises_with_the_code_and_resumes_when_called_again(
    physionet, tmp_path
):
    physionet.script[B] = [Response(404)]
    login = {"username": "alice", "password": "pw"}

    with pytest.raises(m4.ImageFetchError) as caught:
        m4.fetch_images(
            "mimic-cxr-jpg", paths(A, B), credentials=login, target=tmp_path
        )
    result = m4.fetch_images(
        "mimic-cxr-jpg", paths(A, B), credentials=login, target=tmp_path
    )

    assert caught.value.code == "images_incomplete"
    assert caught.value.data["failed"][0]["image_path"] == B
    assert (result["fetched"], result["skipped"]) == (1, 1)
    assert Path(result["root"], B).read_bytes() == IMAGES[B]
