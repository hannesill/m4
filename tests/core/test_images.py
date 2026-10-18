import duckdb
import pytest

from m4.core.images import ImageFiles

CXR = ImageFiles(
    table="mimic_cxr.metadata",
    view="mimic_cxr.images",
    id_column="dicom_id",
    path_template="files/p{subject_id[:2]}/p{subject_id}/s{study_id}/{dicom_id}.jpg",
)
PATH = "files/p10/p10000032/s50414267/02aa804e-bde0afdd-112c0b34-7bc16630-4e384014.jpg"


def test_path_sql_makes_the_path_physionet_keeps_the_image_at():
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE metadata AS SELECT 10000032::BIGINT AS subject_id, "
        "50414267::BIGINT AS study_id, "
        "'02aa804e-bde0afdd-112c0b34-7bc16630-4e384014' AS dicom_id"
    )

    (path,) = con.execute(f"SELECT {CXR.path_sql()} FROM metadata").fetchone()

    assert path == PATH


def test_path_sql_is_null_rather_than_a_wrong_path_when_a_column_is():
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE metadata AS SELECT NULL::BIGINT AS subject_id, "
        "1::BIGINT AS study_id, 'x' AS dicom_id"
    )

    assert con.execute(f"SELECT {CXR.path_sql()} FROM metadata").fetchone() == (None,)


def test_path_sql_quotes_literal_text():
    images = ImageFiles(
        table="s.t", view="s.v", id_column="id", path_template="it's/{id}.png"
    )
    con = duckdb.connect()

    row = con.execute(f"SELECT {images.path_sql()} FROM (SELECT 7 AS id)").fetchone()

    assert row == ("it's/7.png",)


@pytest.mark.parametrize(
    "path",
    [
        PATH,
        # Another of the ten top-level folders
        "files/p19/p19999987/s58971208/abc.jpg",
    ],
)
def test_paths_of_the_datasets_images_are_accepted(path):
    assert CXR.is_image_path(path)


@pytest.mark.parametrize(
    "path",
    [
        "files/p10/p10000032/s50414267/x.dcm",  # not an image of this dataset
        "mimic-cxr-2.0.0-metadata.csv.gz",
        "/files/p10/p10000032/s50414267/x.jpg",
        "files/p10/p10000032/s50414267/sub/x.jpg",
        "files/p100/p10000032/s50414267/x.jpg",  # [:2] takes two characters
        "files/p10/p10000032/s50414267/../x.jpg",
        "files/p10/p10000032/s50414267/",
        # Folders and drives on Windows
        "files/p10/p10000032/s50414267/a\\..\\..\\x.jpg",
        "files/p10/p10000032/s5041:4267/x.jpg",
        "files/p10/p10000032/s50414267/x\x00.jpg",
    ],
)
def test_other_paths_are_refused(path):
    assert not CXR.is_image_path(path)


def test_a_template_placeholder_that_is_a_whole_segment_cannot_climb_out():
    images = ImageFiles(
        table="s.t", view="s.v", id_column="id", path_template="{folder}/{id}.jpg"
    )

    assert images.is_image_path("a/b.jpg")
    assert not images.is_image_path("../b.jpg")
    assert not images.is_image_path("./b.jpg")
    assert not images.is_image_path("C:/b.jpg")
    assert not images.is_image_path("..\\..\\b.jpg")


@pytest.mark.parametrize(
    "fields",
    [
        {"path_template": "files/all.jpg"},  # no placeholder
        {"path_template": "/files/{id}.jpg"},
        {"path_template": "../{id}.jpg"},
        {"path_template": "files//{id}.jpg"},
        {"path_template": "files/{id[:0]}.jpg"},
        {"path_template": "files/{id}}.jpg"},
        {"path_template": "files\\{id}.jpg"},
        {"view": "images"},  # without a schema
        {"view": "mimic_cxr.images; DROP TABLE x"},
        {"table": "Mimic_CXR.metadata"},
        {"id_column": "dicom id"},
    ],
)
def test_image_files_refuse_what_m4_cannot_use(fields):
    values = {
        "table": "s.t",
        "view": "s.v",
        "id_column": "id",
        "path_template": "files/{id}.jpg",
        **fields,
    }

    with pytest.raises(ValueError):
        ImageFiles(**values)
