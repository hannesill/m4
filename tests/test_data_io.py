import base64
import errno
import gzip
import json
from pathlib import Path
from unittest import mock

import duckdb
import pytest
import requests

from m4.core.backends.duckdb import DuckDBBackend
from m4.core.datasets import DatasetDefinition, Modality
from m4.data_io import (
    COMMON_USER_AGENT,
    DatasetDownloadError,
    PhysioNetCredentials,
    _create_duckdb_with_views,
    _download_dataset_files,
    _scrape_urls_from_html_page,
    compute_parquet_dir_size,
    conversion_out_of_reach,
    convert_csv_to_parquet,
    download_dataset,
    find_raw_root,
    find_unconverted,
    folders_without_tables,
    init_duckdb_from_parquet,
    is_dataset_prepared,
    mark_dataset_prepared,
    raw_files_left_to_convert,
    unfinished_conversion,
    verify_table_rowcount,
)


def test_compute_parquet_dir_size_empty(tmp_path):
    size = compute_parquet_dir_size(tmp_path)
    assert size == 0


def test_verify_table_rowcount_with_temp_duckdb(tmp_path):
    db_path = tmp_path / "test.duckdb"
    con = duckdb.connect(str(db_path))
    try:
        con.execute("CREATE VIEW temp_numbers AS SELECT 1 AS x UNION ALL SELECT 2 AS x")
        con.commit()
    finally:
        con.close()

    count = verify_table_rowcount(db_path, "temp_numbers")
    assert count == 2


# ------------------------------------------------------------
# Scraping tests
# ------------------------------------------------------------


class DummyResponse:
    def __init__(self, content, status_code=200, headers=None):
        self.content = content.encode()
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self):
        if not (200 <= self.status_code < 300):
            raise requests.exceptions.HTTPError(response=self)

    @property
    def reason(self):
        return "Error"

    def iter_content(self, chunk_size=1):
        yield from self.content


def test_scrape_urls(monkeypatch):
    html = (
        "<html><body>"
        '<a href="file1.csv.gz">ok</a>'
        '<a href="skip.txt">no</a>'
        "</body></html>"
    )
    dummy = DummyResponse(html)
    session = requests.Session()
    monkeypatch.setattr(session, "get", lambda url, timeout=None: dummy)
    urls = _scrape_urls_from_html_page("http://example.com/", session)
    assert urls == ["http://example.com/file1.csv.gz"]


def test_scrape_no_matching_suffix(monkeypatch):
    html = '<html><body><a href="file1.txt">ok</a></body></html>'
    dummy = DummyResponse(html)
    session = requests.Session()
    monkeypatch.setattr(session, "get", lambda url, timeout=None: dummy)
    urls = _scrape_urls_from_html_page("http://example.com/", session)
    assert urls == []


def test_common_user_agent_header():
    # Ensure the constant is set and looks like a UA string
    assert isinstance(COMMON_USER_AGENT, str)
    assert "Mozilla/" in COMMON_USER_AGENT


def test_download_dataset_uses_credentials_and_preserves_listing_layout(
    tmp_path, monkeypatch
):
    class Response:
        def __init__(self, content=b"", status_code=200, headers=None):
            self.content = content
            self.status_code = status_code
            self.headers = headers or {}
            self.reason = "OK"

        def iter_content(self, chunk_size=8192):
            for index in range(0, len(self.content), chunk_size):
                yield self.content[index : index + chunk_size]

    class Session:
        def __init__(self):
            self.headers = {}
            self.auth = None

        def head(self, url, **kwargs):
            return Response(headers={"content-length": "9", "accept-ranges": "bytes"})

        def get(self, url, **kwargs):
            if url.endswith("/hosp/"):
                return Response(
                    b'<a href="admissions.csv.gz">admissions</a>',
                    headers={"content-length": "9"},
                )
            if url.endswith("/icu/"):
                return Response(b"", headers={"content-length": "0"})
            return Response(b"csv-bytes", headers={"content-length": "9"})

    sessions = []

    def make_session():
        session = Session()
        sessions.append(session)
        return session

    monkeypatch.setattr("m4.data_io.requests.Session", make_session)

    credentials = PhysioNetCredentials(username="alice", password="secret")
    ok = download_dataset("mimic-iv", tmp_path, credentials=credentials)

    assert ok is True
    assert (tmp_path / "hosp" / "admissions.csv.gz").read_bytes() == b"csv-bytes"
    assert (sessions[0].auth.username, sessions[0].auth.password) == (
        "alice",
        "secret",
    )


# ------------------------------------------------------------
# Where a PhysioNet login may go
#
# These tests use the real requests session and replace the transport below
# it, so nothing reaches a network. The login is made up.
# ------------------------------------------------------------

FAKE_LOGIN = PhysioNetCredentials(username="fake-user", password="FAKE-not-a-password")
FAKE_AUTHORIZATION = "Basic " + base64.b64encode(
    b"fake-user:FAKE-not-a-password"
).decode("ascii")


class _SessionWithoutEnvironment(requests.Session):
    """A real session that ignores proxy settings and ~/.netrc, so that a test
    neither reads the developer's setup nor looks any host name up."""

    def __init__(self):
        super().__init__()
        self.trust_env = False


class Wire:
    """Stands in for the network: keeps what would be sent, answers from a script."""

    def __init__(self, monkeypatch, answer):
        self.sent = []
        self._answer = answer
        monkeypatch.setattr("m4.data_io.requests.Session", _SessionWithoutEnvironment)
        monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", self._send)

    def _send(self, request, **kwargs):
        self.sent.append(request)
        status, headers, body = self._answer(request)
        response = requests.Response()
        response.status_code = status
        response.headers.update(headers)
        response._content = body
        response._content_consumed = True
        response.url = request.url
        response.request = request
        return response

    def sent_to(self, prefix):
        return [request for request in self.sent if request.url.startswith(prefix)]


def test_physionet_credentials_never_show_the_password():
    assert FAKE_LOGIN.password == "FAKE-not-a-password"
    for shown in (
        repr(FAKE_LOGIN),
        str(FAKE_LOGIN),
        f"{FAKE_LOGIN}",
        f"{FAKE_LOGIN!r}",
    ):
        assert "FAKE-not-a-password" not in shown
    assert "FAKE-not-a-password" not in repr({"credentials": [FAKE_LOGIN]})


@pytest.mark.parametrize(
    "listing_url",
    [
        "https://example.test/collect/",
        "http://physionet.org/files/mimiciv/3.1/",
        "https://physionet.org.example.test/files/mimiciv/3.1/",
        "https://physionet.org@example.test/files/mimiciv/3.1/",
        "https://physionet.org:8443/files/mimiciv/3.1/",
        "https://www.physionet.org/files/mimiciv/3.1/",
    ],
)
def test_login_is_refused_to_anything_but_physionet_over_https(
    tmp_path, monkeypatch, listing_url
):
    wire = Wire(monkeypatch, lambda request: (200, {}, b""))

    with pytest.raises(DatasetDownloadError) as refused:
        _download_dataset_files(
            "somewhere-else",
            {"file_listing_url": listing_url},
            tmp_path,
            credentials=FAKE_LOGIN,
        )

    assert refused.value.code == "physionet_url_required"
    assert "https://physionet.org/" in refused.value.message
    assert "FAKE-not-a-password" not in refused.value.message
    assert wire.sent == []


def test_login_goes_to_physionet_and_a_link_elsewhere_is_refused(tmp_path, monkeypatch):
    listing = "https://physionet.org/files/made-up/1.0/"

    def answer(request):
        if request.url == listing:
            page = (
                b'<a href="admissions.csv.gz">a</a>'
                b'<a href="https://example.test/patients.csv.gz">b</a>'
            )
            return 200, {}, page
        if request.method == "HEAD":
            return 200, {"content-length": "9"}, b""
        return 200, {"content-length": "9"}, b"csv-bytes"

    wire = Wire(monkeypatch, answer)

    with pytest.raises(DatasetDownloadError) as refused:
        _download_dataset_files(
            "made-up", {"file_listing_url": listing}, tmp_path, credentials=FAKE_LOGIN
        )

    assert refused.value.code == "physionet_url_required"
    assert "example.test" in refused.value.message
    assert (tmp_path / "admissions.csv.gz").read_bytes() == b"csv-bytes"
    assert len(wire.sent) == 3  # the listing, then HEAD and GET of the one file
    assert wire.sent_to("https://physionet.org/") == wire.sent
    assert {r.headers["Authorization"] for r in wire.sent} == {FAKE_AUTHORIZATION}


def test_login_is_dropped_when_physionet_redirects_to_another_host(
    tmp_path, monkeypatch
):
    listing = "https://physionet.org/files/made-up/1.0/"

    def answer(request):
        if request.url == listing:
            return 200, {}, b'<a href="admissions.csv.gz">a</a>'
        if request.url.startswith("https://physionet.org/"):
            return (
                302,
                {"location": "https://example.test/mirror/admissions.csv.gz"},
                b"",
            )
        if request.method == "HEAD":
            return 200, {"content-length": "9"}, b""
        return 200, {"content-length": "9"}, b"csv-bytes"

    wire = Wire(monkeypatch, answer)

    assert _download_dataset_files(
        "made-up", {"file_listing_url": listing}, tmp_path, credentials=FAKE_LOGIN
    )

    elsewhere = wire.sent_to("https://example.test/")
    assert len(elsewhere) == 2  # the redirected HEAD and GET
    assert all("Authorization" not in request.headers for request in elsewhere)
    for request in wire.sent_to("https://physionet.org/"):
        assert request.headers["Authorization"] == FAKE_AUTHORIZATION


def test_download_without_a_login_is_not_tied_to_physionet(tmp_path, monkeypatch):
    listing = "https://example.test/open-data/"

    def answer(request):
        if request.url == listing:
            return 200, {}, b'<a href="table.csv.gz">a</a>'
        if request.method == "HEAD":
            return 200, {"content-length": "9"}, b""
        return 200, {"content-length": "9"}, b"csv-bytes"

    wire = Wire(monkeypatch, answer)

    assert _download_dataset_files("open", {"file_listing_url": listing}, tmp_path)

    assert (tmp_path / "table.csv.gz").read_bytes() == b"csv-bytes"
    assert all("Authorization" not in request.headers for request in wire.sent)


# ------------------------------------------------------------
# CSV -> Parquet conversion and DuckDB init tests
# ------------------------------------------------------------


def _write_gz_csv(path, text):
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(text)


def test_convert_csv_to_parquet_and_init_duckdb(tmp_path, monkeypatch):
    # Prepare a minimal CSV.gz under hosp/
    src_root = tmp_path / "src"
    hosp_dir = src_root / "hosp"
    hosp_dir.mkdir(parents=True, exist_ok=True)
    csv_gz = hosp_dir / "sample.csv.gz"

    _write_gz_csv(
        csv_gz,
        "col1,col2\n"  # header
        "1,foo\n"
        "2,bar\n",
    )

    # Convert to Parquet under dst root
    dst_root = tmp_path / "parquet"
    ok = convert_csv_to_parquet("mimic-iv-demo", src_root, dst_root)
    assert ok  # conversion succeeded

    out_parquet = dst_root / "hosp" / "sample.parquet"
    assert out_parquet.exists()  # parquet file created

    # Quick verify via DuckDB
    con = duckdb.connect()
    try:
        cnt = con.execute(
            f"SELECT COUNT(*) FROM read_parquet('{out_parquet.as_posix()}')"
        ).fetchone()[0]
    finally:
        con.close()
    assert cnt == 2  # two data rows

    # Initialize DuckDB views, patching the parquet root resolver.
    # mimic-iv-demo has schema_mapping {"hosp": "mimiciv_hosp", "icu": "mimiciv_icu"},
    # so views are schema-qualified: mimiciv_hosp.sample
    db_path = tmp_path / "test.duckdb"
    with mock.patch("m4.data_io.get_dataset_parquet_root", return_value=dst_root):
        init_ok = init_duckdb_from_parquet("mimic-iv-demo", db_path)
    assert init_ok  # views created

    # Query the schema-qualified view
    con = duckdb.connect(str(db_path))
    try:
        cnt = con.execute("SELECT COUNT(*) FROM mimiciv_hosp.sample").fetchone()[0]
    finally:
        con.close()
    assert cnt == 2


def test_failed_conversion_leaves_no_table_and_a_second_run_finishes_it(tmp_path):
    src_root = tmp_path / "src"
    (src_root / "hosp").mkdir(parents=True)
    _write_gz_csv(src_root / "hosp" / "admissions.csv.gz", "subject_id\n1\n2\n")
    broken = src_root / "hosp" / "patients.csv.gz"
    broken.write_bytes(b"this is not gzip")
    dst_root = tmp_path / "parquet"

    assert not convert_csv_to_parquet("mimic-iv-demo", src_root, dst_root)

    # The table that failed is not there in any form, and the folder says so.
    assert sorted(p.name for p in dst_root.rglob("*") if p.is_file()) == [
        ".m4-converting.json",
        "admissions.parquet",
    ]
    assert unfinished_conversion(dst_root) == (
        str(src_root.resolve()),
        ["hosp/patients.parquet"],
    )
    assert find_unconverted(src_root, dst_root) == [broken]

    _write_gz_csv(broken, "subject_id,gender\n1,F\n")

    assert convert_csv_to_parquet("mimic-iv-demo", src_root, dst_root)
    assert find_unconverted(src_root, dst_root) == []
    assert unfinished_conversion(dst_root) is None
    assert sorted(p.name for p in dst_root.rglob("*") if p.is_file()) == [
        "admissions.parquet",
        "patients.parquet",
    ]


def test_prepared_mark_is_for_one_database_over_one_parquet_folder(tmp_path):
    parquet_root = tmp_path / "old" / "parquet"
    _create_parquet(parquet_root / "hosp", "admissions", "subject_id\n1\n")
    db_path = tmp_path / "old" / "mimic.duckdb"
    db_path.touch()

    assert not is_dataset_prepared(parquet_root, db_path)
    mark_dataset_prepared(parquet_root, db_path)
    assert is_dataset_prepared(parquet_root, db_path)

    # Another database over the same files was not initialized by that run.
    assert not is_dataset_prepared(parquet_root, tmp_path / "old" / "other.duckdb")

    # Views name their Parquet files by absolute path, so a data directory
    # that was moved needs `m4 init` again.
    (tmp_path / "old").rename(tmp_path / "new")
    assert not is_dataset_prepared(
        tmp_path / "new" / "parquet", tmp_path / "new" / "mimic.duckdb"
    )


MIMIC_IV_MAPPING = {
    "hosp": "mimiciv_hosp",
    "icu": "mimiciv_icu",
    "derived": "mimiciv_derived",
}


def _touch_raw(root, *names):
    for name in names:
        path = root / f"{name}.csv.gz"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    return root


def test_find_raw_root_accepts_the_folder_the_dataset_is_laid_out_in(tmp_path):
    root = _touch_raw(tmp_path, "hosp/admissions", "icu/icustays")

    assert find_raw_root(root, MIMIC_IV_MAPPING) == root


def test_find_raw_root_finds_the_version_folder_below_a_wget_tree(tmp_path):
    version = _touch_raw(
        tmp_path / "physionet.org" / "files" / "mimiciv" / "3.1",
        "hosp/admissions",
        "icu/icustays",
    )

    assert find_raw_root(tmp_path, MIMIC_IV_MAPPING) == version
    assert find_raw_root(tmp_path / "physionet.org", MIMIC_IV_MAPPING) == version


def test_find_raw_root_for_files_that_belong_at_the_top_level(tmp_path):
    # eICU keeps every table directly in its folder.
    version = _touch_raw(tmp_path / "files" / "eicu-crd" / "2.0", "patient", "lab")

    assert find_raw_root(tmp_path, {"": "eicu_crd"}) == version
    assert find_raw_root(version, {"": "eicu_crd"}) == version


def test_find_raw_root_prefers_the_folder_above_a_single_schema_folder(tmp_path):
    # mimic-iv-note is accepted both as note/*.csv.gz and as bare files.
    version = _touch_raw(tmp_path / "files" / "mimic-iv-note" / "2.2", "note/discharge")

    assert find_raw_root(tmp_path, {"note": "mimiciv_note"}) == version
    assert find_raw_root(version / "note", {"note": "mimiciv_note"}) == version / "note"


def test_find_raw_root_without_a_fitting_folder(tmp_path):
    root = _touch_raw(tmp_path, "admissions", "other/icustays")

    assert find_raw_root(root, MIMIC_IV_MAPPING) is None


def test_find_raw_root_without_a_schema_mapping_takes_any_layout(tmp_path):
    root = _touch_raw(tmp_path, "anything/goes/table")

    assert find_raw_root(root, None) == root


def test_raw_files_left_to_convert_are_those_without_a_finished_table(tmp_path):
    raw_root = _touch_raw(tmp_path / "raw", "hosp/admissions", "icu/icustays")
    parquet_root = tmp_path / "parquet"
    _create_parquet(parquet_root / "hosp", "admissions", "subject_id\n1\n")
    waiting = [raw_root / "icu" / "icustays.csv.gz"]

    assert (
        raw_files_left_to_convert(raw_root, parquet_root, MIMIC_IV_MAPPING) == waiting
    )

    table = _create_parquet(parquet_root / "icu", "icustays", "subject_id\n1\n")
    assert raw_files_left_to_convert(raw_root, parquet_root, MIMIC_IV_MAPPING) == []

    # A table that was cut short is no table.
    table.write_bytes(table.read_bytes()[:40])
    assert (
        raw_files_left_to_convert(raw_root, parquet_root, MIMIC_IV_MAPPING) == waiting
    )


def test_raw_files_left_to_convert_are_looked_for_where_init_reads_them(tmp_path):
    # A wget tree in M4's raw folder: init names the folder deeper down, and
    # converts from there.
    raw_root = tmp_path / "raw"
    nested = _touch_raw(
        raw_root / "physionet.org" / "files" / "mimiciv" / "3.1", "hosp/admissions"
    )
    parquet_root = tmp_path / "parquet"

    assert raw_files_left_to_convert(raw_root, parquet_root, MIMIC_IV_MAPPING) == [
        nested / "hosp" / "admissions.csv.gz"
    ]

    _create_parquet(parquet_root / "hosp", "admissions", "subject_id\n1\n")
    assert raw_files_left_to_convert(raw_root, parquet_root, MIMIC_IV_MAPPING) == []

    # Files that init cannot place are not waited for: no run converts them.
    unplaced = _touch_raw(tmp_path / "unplaced", "admissions", "other/icustays")
    assert raw_files_left_to_convert(unplaced, parquet_root, MIMIC_IV_MAPPING) == []
    # Neither is a folder that is not there, with or without a mapping.
    missing = tmp_path / "missing"
    assert raw_files_left_to_convert(missing, parquet_root, MIMIC_IV_MAPPING) == []
    assert raw_files_left_to_convert(missing, parquet_root, None) == []


def test_folders_without_tables_counts_raw_files_and_tables_alike(tmp_path):
    raw_root = _touch_raw(tmp_path / "raw", "hosp/admissions")
    parquet_root = tmp_path / "parquet"
    folders = ["hosp", "icu"]

    assert folders_without_tables(
        folders, MIMIC_IV_MAPPING, raw_root, parquet_root
    ) == ["icu"]

    # Tables from an earlier run fill a folder as raw files do.
    _create_parquet(parquet_root / "icu", "icustays", "subject_id\n1\n")
    assert (
        folders_without_tables(folders, MIMIC_IV_MAPPING, raw_root, parquet_root) == []
    )

    # Bare files fill the one folder of a dataset of one schema.
    note_mapping = {"note": "mimiciv_note"}
    bare = _touch_raw(tmp_path / "bare", "discharge")
    nothing = tmp_path / "nothing"
    assert folders_without_tables(["note"], note_mapping, bare, nothing) == []
    assert folders_without_tables(["note"], note_mapping, nothing, nothing) == ["note"]

    # A dataset without a mapping has no folders to fill.
    assert folders_without_tables(folders, None, raw_root, nothing) == []
    assert folders_without_tables(folders, {}, raw_root, nothing) == []


def test_no_view_created_is_a_failure(tmp_path):
    """Parquet files that all sit outside the mapped folders give an empty
    database, which must not pass for an initialized one."""
    parquet_root = tmp_path / "parquet"
    _create_parquet(
        parquet_root / "files" / "mimiciv" / "3.1" / "hosp",
        "admissions",
        "subject_id,hadm_id\n1,100\n",
    )

    ok = _create_duckdb_with_views(
        tmp_path / "test.duckdb", parquet_root, schema_mapping=MIMIC_IV_MAPPING
    )

    assert not ok


# ------------------------------------------------------------
# Schema mapping tests
# ------------------------------------------------------------


def _create_parquet(directory, filename, csv_text):
    """Helper: write a CSV.gz, convert to parquet, return path."""
    directory.mkdir(parents=True, exist_ok=True)
    csv_gz = directory / f"{filename}.csv.gz"
    _write_gz_csv(csv_gz, csv_text)
    parquet_path = directory / f"{filename}.parquet"
    con = duckdb.connect()
    try:
        con.execute(
            f"COPY (SELECT * FROM read_csv_auto('{csv_gz.as_posix()}')) "
            f"TO '{parquet_path.as_posix()}' (FORMAT PARQUET)"
        )
    finally:
        con.close()
    return parquet_path


def test_schema_mapping_hosp_and_icu(tmp_path):
    """Parquet files in hosp/ and icu/ with schema_mapping produce
    schema-qualified DuckDB views."""
    parquet_root = tmp_path / "parquet"
    _create_parquet(
        parquet_root / "hosp", "admissions", "subject_id,hadm_id\n1,100\n2,200\n"
    )
    _create_parquet(
        parquet_root / "icu", "icustays", "subject_id,stay_id\n1,10\n2,20\n"
    )

    db_path = tmp_path / "test.duckdb"
    mapping = {"hosp": "mimiciv_hosp", "icu": "mimiciv_icu"}
    ok = _create_duckdb_with_views(db_path, parquet_root, schema_mapping=mapping)
    assert ok

    con = duckdb.connect(str(db_path))
    try:
        # Schemas exist
        schemas = [
            r[0]
            for r in con.execute(
                "SELECT schema_name FROM information_schema.schemata"
            ).fetchall()
        ]
        assert "mimiciv_hosp" in schemas
        assert "mimiciv_icu" in schemas

        # Views are schema-qualified
        cnt = con.execute("SELECT COUNT(*) FROM mimiciv_hosp.admissions").fetchone()[0]
        assert cnt == 2
        cnt = con.execute("SELECT COUNT(*) FROM mimiciv_icu.icustays").fetchone()[0]
        assert cnt == 2
    finally:
        con.close()


def test_schema_mapping_root_level(tmp_path):
    """Root-level parquet files with {"": "eicu_crd"} mapping produce
    eicu_crd.table views."""
    parquet_root = tmp_path / "parquet"
    _create_parquet(parquet_root, "patient", "patientunitstayid,age\n1,65\n2,42\n")

    db_path = tmp_path / "test.duckdb"
    mapping = {"": "eicu_crd"}
    ok = _create_duckdb_with_views(db_path, parquet_root, schema_mapping=mapping)
    assert ok

    con = duckdb.connect(str(db_path))
    try:
        cnt = con.execute("SELECT COUNT(*) FROM eicu_crd.patient").fetchone()[0]
        assert cnt == 2
    finally:
        con.close()


def test_schema_mapping_flat_files_single_schema_fallback(tmp_path):
    """Flat parquet files with a single-schema mapping (e.g. mimic-iv-note
    with {"note": "mimiciv_note"}) should fall back to that schema."""
    parquet_root = tmp_path / "parquet"
    _create_parquet(parquet_root, "discharge", "subject_id,note\n1,text\n2,more\n")
    _create_parquet(parquet_root, "radiology", "subject_id,note\n3,xray\n")

    db_path = tmp_path / "test.duckdb"
    mapping = {"note": "mimiciv_note"}
    ok = _create_duckdb_with_views(db_path, parquet_root, schema_mapping=mapping)
    assert ok

    con = duckdb.connect(str(db_path))
    try:
        cnt = con.execute("SELECT COUNT(*) FROM mimiciv_note.discharge").fetchone()[0]
        assert cnt == 2
        cnt = con.execute("SELECT COUNT(*) FROM mimiciv_note.radiology").fetchone()[0]
        assert cnt == 1
    finally:
        con.close()


def test_mimiciv_derived_schema_not_created_during_init(tmp_path):
    """The mimiciv_derived schema should NOT be created during normal init.
    It is created by m4 init-derived (materializer.py) when needed."""
    parquet_root = tmp_path / "parquet"
    _create_parquet(
        parquet_root / "hosp", "admissions", "subject_id,hadm_id\n1,100\n2,200\n"
    )
    _create_parquet(
        parquet_root / "icu", "icustays", "subject_id,stay_id\n1,10\n2,20\n"
    )

    db_path = tmp_path / "test.duckdb"
    mapping = {
        "hosp": "mimiciv_hosp",
        "icu": "mimiciv_icu",
        "derived": "mimiciv_derived",
    }
    ok = _create_duckdb_with_views(db_path, parquet_root, schema_mapping=mapping)
    assert ok

    con = duckdb.connect(str(db_path))
    try:
        schemas = [
            r[0]
            for r in con.execute(
                "SELECT schema_name FROM information_schema.schemata"
            ).fetchall()
        ]
        assert "mimiciv_hosp" in schemas
        assert "mimiciv_icu" in schemas
        assert "mimiciv_derived" not in schemas
    finally:
        con.close()


def test_no_schema_mapping_flat_naming(tmp_path):
    """Without schema_mapping, views use flat naming (backward compat)."""
    parquet_root = tmp_path / "parquet"
    _create_parquet(parquet_root / "hosp", "admissions", "subject_id,hadm_id\n1,100\n")

    db_path = tmp_path / "test.duckdb"
    ok = _create_duckdb_with_views(db_path, parquet_root, schema_mapping=None)
    assert ok

    con = duckdb.connect(str(db_path))
    try:
        cnt = con.execute("SELECT COUNT(*) FROM hosp_admissions").fetchone()[0]
        assert cnt == 1
    finally:
        con.close()


# ------------------------------------------------------------
# Round-trip integration test: parquet → DuckDB → backend API
# ------------------------------------------------------------


def test_roundtrip_parquet_to_backend_api(tmp_path):
    """End-to-end: create parquet, init DuckDB with schema_mapping,
    then verify get_table_list / get_table_info / get_sample_data
    all work through the DuckDBBackend API."""
    parquet_root = tmp_path / "parquet"
    _create_parquet(
        parquet_root / "hosp",
        "patients",
        "subject_id,gender,anchor_age\n1,M,65\n2,F,42\n",
    )
    _create_parquet(
        parquet_root / "icu",
        "icustays",
        "subject_id,stay_id\n1,10\n2,20\n",
    )

    mapping = {"hosp": "mimiciv_hosp", "icu": "mimiciv_icu"}
    db_path = tmp_path / "roundtrip.duckdb"
    ok = _create_duckdb_with_views(db_path, parquet_root, schema_mapping=mapping)
    assert ok

    ds = DatasetDefinition(
        name="roundtrip-test",
        modalities=frozenset({Modality.TABULAR}),
        schema_mapping=mapping,
    )
    backend = DuckDBBackend(db_path_override=db_path)

    # get_table_list returns schema-qualified names
    tables = backend.get_table_list(ds)
    assert "mimiciv_hosp.patients" in tables
    assert "mimiciv_icu.icustays" in tables

    # get_table_info works for schema-qualified names
    info = backend.get_table_info("mimiciv_hosp.patients", ds)
    assert info.success is True
    col_names = info.dataframe["name"].tolist()
    assert "subject_id" in col_names
    assert "gender" in col_names

    # get_sample_data works for schema-qualified names
    sample = backend.get_sample_data("mimiciv_hosp.patients", ds, limit=1)
    assert sample.success is True
    assert sample.row_count <= 1
    assert "subject_id" in sample.dataframe.columns


def test_unfinished_conversion_is_not_settled_by_converting_another_folder(tmp_path):
    first = tmp_path / "first"
    (first / "hosp").mkdir(parents=True)
    _write_gz_csv(first / "hosp" / "admissions.csv.gz", "subject_id\n1\n2\n")
    broken = first / "hosp" / "patients.csv.gz"
    broken.write_bytes(b"this is not gzip")
    dst_root = tmp_path / "parquet"
    assert not convert_csv_to_parquet("mimic-iv-demo", first, dst_root)

    # A folder without the raw file of the table that failed converts what it
    # holds, and leaves the first conversion as unfinished as it was.
    second = tmp_path / "second"
    (second / "hosp").mkdir(parents=True)
    _write_gz_csv(second / "hosp" / "admissions.csv.gz", "subject_id\n1\n2\n")
    _write_gz_csv(second / "hosp" / "transfers.csv.gz", "subject_id\n1\n")

    assert convert_csv_to_parquet("mimic-iv-demo", second, dst_root)
    assert (dst_root / "hosp" / "transfers.parquet").exists()
    assert unfinished_conversion(dst_root) == (
        str(first.resolve()),
        ["hosp/patients.parquet"],
    )

    _write_gz_csv(broken, "subject_id,gender\n1,F\n")

    assert convert_csv_to_parquet("mimic-iv-demo", first, dst_root)
    assert unfinished_conversion(dst_root) is None
    assert not (dst_root / ".m4-converting.json").exists()


def test_failed_conversion_is_finished_from_its_own_folder_without_the_bad_file(
    tmp_path,
):
    src_root = tmp_path / "src"
    (src_root / "hosp").mkdir(parents=True)
    _write_gz_csv(src_root / "hosp" / "admissions.csv.gz", "subject_id\n1\n2\n")
    # What macOS leaves beside a file on a drive that cannot keep its attributes.
    junk = src_root / "hosp" / "._admissions.csv.gz"
    junk.write_bytes(b"\x00\x05\x16\x07 not a table")
    dst_root = tmp_path / "parquet"

    assert not convert_csv_to_parquet("mimic-iv-demo", src_root, dst_root)
    assert unfinished_conversion(dst_root) is not None

    # Another folder would have to bring the table that failed. The folder
    # the conversion read from finishes it with whatever it holds by then.
    other = _touch_raw(tmp_path / "other", "hosp/admissions")
    assert conversion_out_of_reach(dst_root, other) == str(src_root.resolve())
    assert conversion_out_of_reach(dst_root, src_root) is None

    junk.unlink()

    assert conversion_out_of_reach(dst_root, src_root) is None
    assert convert_csv_to_parquet("mimic-iv-demo", src_root, dst_root)
    assert unfinished_conversion(dst_root) is None
    assert sorted(p.name for p in dst_root.rglob("*") if p.is_file()) == [
        "admissions.parquet"
    ]


def test_conversion_note_without_its_tables_is_only_settled_from_its_own_folder(
    tmp_path,
):
    # For a short time M4 noted the folder an unfinished conversion read from,
    # and not the tables it was to make. Which of them are missing is then
    # unknown, so no other folder can be taken to finish it.
    first = tmp_path / "first"
    (first / "hosp").mkdir(parents=True)
    _write_gz_csv(first / "hosp" / "admissions.csv.gz", "subject_id\n1\n2\n")
    _write_gz_csv(first / "hosp" / "patients.csv.gz", "subject_id,gender\n1,F\n")
    second = tmp_path / "second"
    (second / "hosp").mkdir(parents=True)
    _write_gz_csv(second / "hosp" / "admissions.csv.gz", "subject_id\n1\n2\n")
    dst_root = tmp_path / "parquet"
    dst_root.mkdir()
    note = dst_root / ".m4-converting.json"
    note.write_text(json.dumps({"version": 1, "source": str(first.resolve())}))

    assert convert_csv_to_parquet("mimic-iv-demo", second, dst_root)
    assert convert_csv_to_parquet("mimic-iv-demo", second, dst_root)
    assert unfinished_conversion(dst_root) == (str(first.resolve()), None)

    assert convert_csv_to_parquet("mimic-iv-demo", first, dst_root)
    assert unfinished_conversion(dst_root) is None
    assert not note.exists()


# ------------------------------------------------------------
# A download says of itself whether it finished
# ------------------------------------------------------------

DOWNLOAD_NOTE = ".m4-downloading.json"


def test_download_is_noted_as_unfinished_until_every_file_arrived(
    tmp_path, monkeypatch
):
    listing = "https://example.test/open-data/"
    out_of_reach = {"second.csv.gz"}

    def answer(request):
        if request.url == listing:
            return 200, {}, b'<a href="first.csv.gz">a</a><a href="second.csv.gz">b</a>'
        if request.url.rsplit("/", 1)[1] in out_of_reach:
            return 503, {}, b""
        if request.method == "HEAD":
            return 200, {"content-length": "9"}, b""
        return 200, {"content-length": "9"}, b"csv-bytes"

    Wire(monkeypatch, answer)

    with pytest.raises(DatasetDownloadError) as failed:
        _download_dataset_files("open", {"file_listing_url": listing}, tmp_path)

    # One file is there, and nothing but the note says that one is missing.
    assert failed.value.code == "download_network_failed"
    assert (tmp_path / "first.csv.gz").read_bytes() == b"csv-bytes"
    assert (tmp_path / DOWNLOAD_NOTE).exists()

    out_of_reach.clear()

    assert _download_dataset_files("open", {"file_listing_url": listing}, tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "first.csv.gz",
        "second.csv.gz",
    ]


def test_download_into_a_folder_that_cannot_be_noted_fetches_nothing(
    tmp_path, monkeypatch
):
    listing = "https://example.test/open-data/"

    def answer(request):
        if request.url == listing:
            return 200, {}, b'<a href="table.csv.gz">a</a>'
        if request.method == "HEAD":
            return 200, {"content-length": "9"}, b""
        return 200, {"content-length": "9"}, b"csv-bytes"

    wire = Wire(monkeypatch, answer)
    real_write_text = Path.write_text

    def write_text(self, *args, **kwargs):
        if self.name.startswith(DOWNLOAD_NOTE):
            raise OSError(28, "No space left on device", str(self))
        return real_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", write_text)

    with pytest.raises(DatasetDownloadError) as failed:
        _download_dataset_files("open", {"file_listing_url": listing}, tmp_path)

    # Without the note, files that arrive could pass for a whole download.
    assert failed.value.code == "download_filesystem_failed"
    assert [request.method for request in wire.sent] == ["GET", "HEAD"]
    assert not list(tmp_path.rglob("*.csv.gz*"))


def test_download_that_gets_no_listing_leaves_no_note(tmp_path, monkeypatch):
    listing = "https://physionet.org/files/made-up/1.0/"
    Wire(monkeypatch, lambda request: (401, {}, b""))

    with pytest.raises(DatasetDownloadError) as refused:
        _download_dataset_files(
            "made-up", {"file_listing_url": listing}, tmp_path, credentials=FAKE_LOGIN
        )

    # Nothing was downloaded, so there is nothing to finish.
    assert refused.value.code == "physionet_auth_failed"
    assert list(tmp_path.iterdir()) == []


def test_download_that_finds_every_file_complete_writes_nothing(tmp_path, monkeypatch):
    listing = "https://example.test/open-data/"

    def answer(request):
        if request.url == listing:
            return 200, {}, b'<a href="table.csv.gz">a</a>'
        if request.method == "HEAD":
            return 200, {"content-length": "9"}, b""
        return 200, {"content-length": "9"}, b"csv-bytes"

    wire = Wire(monkeypatch, answer)
    assert _download_dataset_files("open", {"file_listing_url": listing}, tmp_path)
    wire.sent.clear()

    # Going over a whole download again must work in a folder that cannot be
    # written to, and being killed while doing so must leave no note.
    def no_writing(*args, **kwargs):
        raise AssertionError("Nothing is to be written.")

    def read_only(self, *args, **kwargs):
        # What a read-only mount answers, whether or not the file is there.
        raise OSError(errno.EROFS, "Read-only file system", str(self))

    monkeypatch.setattr("m4.data_io._write_marker", no_writing)
    monkeypatch.setattr(Path, "unlink", read_only)

    assert _download_dataset_files("open", {"file_listing_url": listing}, tmp_path)
    assert [request.method for request in wire.sent] == ["GET", "HEAD"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["table.csv.gz"]
