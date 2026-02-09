"""Tests for the files integration (output directory management).

Tests cover:
- register_output_dir() creates directory, stores in meta.json
- register_output_dir(path=...) external directory
- list_output_files() returns correct listing
- get_output_file_path() resolves paths, blocks traversal
- Server endpoints: /api/studies/{study}/files, files/{path}, files-archive
- File preview for each type (text, csv, parquet, image)
- Export with files included
"""

import json
import zipfile

import pytest

from m4.vitrine.study_manager import StudyManager


@pytest.fixture
def vitrine_dir(tmp_path):
    d = tmp_path / ".vitrine"
    d.mkdir()
    return d


@pytest.fixture
def manager(vitrine_dir):
    return StudyManager(vitrine_dir)


# ================================================================
# Stream 1: register_output_dir + StudyManager methods
# ================================================================


class TestRegisterOutputDir:
    def test_creates_self_contained_dir(self, manager):
        manager.get_or_create_study("test-study")
        output = manager.register_output_dir("test-study")
        assert output.exists()
        assert output.name == "output"

    def test_stores_in_meta_json(self, manager):
        manager.get_or_create_study("meta-test")
        manager.register_output_dir("meta-test")
        dir_name = manager._label_to_dir["meta-test"]
        meta_path = manager._studies_dir / dir_name / "meta.json"
        meta = json.loads(meta_path.read_text())
        assert meta["output_dir"] == "output"

    def test_returns_path(self, manager):
        manager.get_or_create_study("path-test")
        output = manager.register_output_dir("path-test")
        assert output.is_absolute()

    def test_external_dir(self, manager, tmp_path):
        ext_dir = tmp_path / "external_output"
        manager.get_or_create_study("ext-test")
        output = manager.register_output_dir("ext-test", path=str(ext_dir))
        assert output.exists()
        assert output == ext_dir.resolve()
        # Meta should store absolute path
        dir_name = manager._label_to_dir["ext-test"]
        meta = json.loads((manager._studies_dir / dir_name / "meta.json").read_text())
        assert meta["output_dir"] == str(ext_dir.resolve())

    def test_nonexistent_study_raises(self, manager):
        with pytest.raises(ValueError, match="not found"):
            manager.register_output_dir("nonexistent")

    def test_idempotent(self, manager):
        manager.get_or_create_study("idem-test")
        out1 = manager.register_output_dir("idem-test")
        out2 = manager.register_output_dir("idem-test")
        assert out1 == out2


class TestGetOutputDir:
    def test_returns_path_after_register(self, manager):
        manager.get_or_create_study("get-test")
        manager.register_output_dir("get-test")
        result = manager.get_output_dir("get-test")
        assert result is not None
        assert result.exists()

    def test_returns_none_when_not_registered(self, manager):
        manager.get_or_create_study("no-output")
        assert manager.get_output_dir("no-output") is None

    def test_returns_none_for_nonexistent_study(self, manager):
        assert manager.get_output_dir("nonexistent") is None


class TestListOutputFiles:
    def test_lists_files(self, manager):
        manager.get_or_create_study("list-test")
        output = manager.register_output_dir("list-test")
        (output / "script.py").write_text("print('hello')")
        (output / "data.csv").write_text("a,b\n1,2")

        files = manager.list_output_files("list-test")
        names = {f["name"] for f in files if not f["is_dir"]}
        assert names == {"script.py", "data.csv"}

    def test_file_types(self, manager):
        manager.get_or_create_study("type-test")
        output = manager.register_output_dir("type-test")
        (output / "code.py").write_text("pass")
        (output / "notes.md").write_text("# Notes")
        (output / "data.csv").write_text("x\n1")

        files = manager.list_output_files("type-test")
        type_map = {f["name"]: f["type"] for f in files if not f["is_dir"]}
        assert type_map["code.py"] == "python"
        assert type_map["notes.md"] == "markdown"
        assert type_map["data.csv"] == "csv"

    def test_nested_files(self, manager):
        manager.get_or_create_study("nested-test")
        output = manager.register_output_dir("nested-test")
        subdir = output / "results"
        subdir.mkdir()
        (subdir / "output.txt").write_text("result")

        files = manager.list_output_files("nested-test")
        paths = {f["path"] for f in files if not f["is_dir"]}
        assert "results/output.txt" in paths

    def test_empty_dir(self, manager):
        manager.get_or_create_study("empty-test")
        manager.register_output_dir("empty-test")
        assert manager.list_output_files("empty-test") == []

    def test_no_output_dir(self, manager):
        manager.get_or_create_study("no-dir")
        assert manager.list_output_files("no-dir") == []

    def test_includes_size_and_modified(self, manager):
        manager.get_or_create_study("size-test")
        output = manager.register_output_dir("size-test")
        (output / "test.txt").write_text("hello world")

        files = manager.list_output_files("size-test")
        txt = next(f for f in files if f["name"] == "test.txt")
        assert txt["size"] > 0
        assert txt["modified"] is not None


class TestGetOutputFilePath:
    def test_resolves_valid_path(self, manager):
        manager.get_or_create_study("resolve-test")
        output = manager.register_output_dir("resolve-test")
        (output / "test.py").write_text("pass")

        result = manager.get_output_file_path("resolve-test", "test.py")
        assert result is not None
        assert result.exists()
        assert result.name == "test.py"

    def test_nested_path(self, manager):
        manager.get_or_create_study("nested-resolve")
        output = manager.register_output_dir("nested-resolve")
        sub = output / "sub"
        sub.mkdir()
        (sub / "data.csv").write_text("a\n1")

        result = manager.get_output_file_path("nested-resolve", "sub/data.csv")
        assert result is not None
        assert result.name == "data.csv"

    def test_blocks_traversal(self, manager):
        manager.get_or_create_study("traverse-test")
        manager.register_output_dir("traverse-test")

        # Try to escape the output dir
        assert manager.get_output_file_path("traverse-test", "../meta.json") is None
        assert (
            manager.get_output_file_path("traverse-test", "../../studies.json") is None
        )

    def test_nonexistent_file(self, manager):
        manager.get_or_create_study("missing-file")
        manager.register_output_dir("missing-file")
        assert manager.get_output_file_path("missing-file", "no-such.txt") is None

    def test_no_output_dir(self, manager):
        manager.get_or_create_study("no-dir-path")
        assert manager.get_output_file_path("no-dir-path", "file.txt") is None


# ================================================================
# Stream 2: Server endpoints
# ================================================================


class TestServerFileEndpoints:
    """Test the file-related HTTP endpoints via ASGI test client."""

    @pytest.fixture
    def study_with_files(self, vitrine_dir):
        """Create a study with output files for testing."""
        mgr = StudyManager(vitrine_dir)
        mgr.get_or_create_study("server-test")
        output = mgr.register_output_dir("server-test")

        # Create test files
        (output / "script.py").write_text("print('hello')")
        (output / "notes.md").write_text("# Notes\nSome text")
        (output / "data.csv").write_text("name,value\nalice,1\nbob,2")
        (output / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        sub = output / "results"
        sub.mkdir()
        (sub / "output.txt").write_text("result data")

        return mgr

    @pytest.fixture
    def client(self, study_with_files):
        from starlette.testclient import TestClient

        from m4.vitrine.server import DisplayServer

        server = DisplayServer(study_manager=study_with_files)
        return TestClient(server._app)

    def test_list_files(self, client):
        resp = client.get("/api/studies/server-test/files")
        assert resp.status_code == 200
        files = resp.json()
        names = {f["name"] for f in files if not f.get("is_dir")}
        assert "script.py" in names
        assert "notes.md" in names
        assert "data.csv" in names

    def test_list_files_nonexistent_study(self, client):
        resp = client.get("/api/studies/nonexistent/files")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_preview_text_file(self, client):
        resp = client.get("/api/studies/server-test/files/script.py")
        assert resp.status_code == 200
        assert "text/plain" in resp.headers["content-type"]
        assert "print('hello')" in resp.text

    def test_preview_markdown(self, client):
        resp = client.get("/api/studies/server-test/files/notes.md")
        assert resp.status_code == 200
        assert "text/plain" in resp.headers["content-type"]
        assert "# Notes" in resp.text

    def test_preview_csv(self, client):
        resp = client.get("/api/studies/server-test/files/data.csv")
        assert resp.status_code == 200
        data = resp.json()
        assert "columns" in data
        assert "rows" in data
        assert data["total_rows"] == 2
        assert "name" in data["columns"]

    def test_preview_image(self, client):
        resp = client.get("/api/studies/server-test/files/image.png")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"

    def test_download_mode(self, client):
        resp = client.get("/api/studies/server-test/files/script.py?mode=download")
        assert resp.status_code == 200
        assert "attachment" in resp.headers.get("content-disposition", "")

    def test_nested_file(self, client):
        resp = client.get("/api/studies/server-test/files/results/output.txt")
        assert resp.status_code == 200
        assert "result data" in resp.text

    def test_file_not_found(self, client):
        resp = client.get("/api/studies/server-test/files/nonexistent.txt")
        assert resp.status_code == 404

    def test_path_traversal_blocked(self, study_with_files):
        """Path traversal is blocked by get_output_file_path (unit level).

        The HTTP client normalizes '../' before it reaches the endpoint,
        so we test traversal protection directly on the manager method.
        """
        mgr = study_with_files
        assert mgr.get_output_file_path("server-test", "../meta.json") is None
        assert mgr.get_output_file_path("server-test", "../../studies.json") is None

    def test_files_archive(self, client):
        resp = client.get("/api/studies/server-test/files-archive")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"
        # Verify it's valid zip
        import io

        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        names = zf.namelist()
        assert "script.py" in names
        assert "results/output.txt" in names

    def test_files_archive_no_output(self, client, vitrine_dir):
        """Archive for a study with no output dir returns 404."""
        mgr = StudyManager(vitrine_dir)
        mgr.get_or_create_study("no-output")
        # Don't register output dir
        resp = client.get("/api/studies/no-output/files-archive")
        assert resp.status_code == 404


# ================================================================
# Stream 4: Export with files
# ================================================================


class TestExportWithFiles:
    @pytest.fixture
    def study_with_files(self, vitrine_dir):
        mgr = StudyManager(vitrine_dir)
        mgr.get_or_create_study("export-test")
        output = mgr.register_output_dir("export-test")
        (output / "protocol.md").write_text("# Protocol\nTest protocol")
        (output / "analysis.py").write_text("import pandas as pd")
        (output / "data.csv").write_text("x,y\n1,2\n3,4")
        return mgr

    def test_html_export_includes_files(self, study_with_files, tmp_path):
        from m4.vitrine.export import export_html

        out = tmp_path / "export.html"
        export_html(study_with_files, out, study="export-test")
        html = out.read_text()
        assert "Research Files" in html
        assert "protocol.md" in html
        assert "analysis.py" in html

    def test_html_export_inlines_text(self, study_with_files, tmp_path):
        from m4.vitrine.export import export_html

        out = tmp_path / "export.html"
        export_html(study_with_files, out, study="export-test")
        html = out.read_text()
        assert "import pandas as pd" in html
        assert "# Protocol" in html

    def test_json_export_includes_output_files(self, study_with_files, tmp_path):
        from m4.vitrine.export import export_json

        out = tmp_path / "export.zip"
        export_json(study_with_files, out, study="export-test")
        zf = zipfile.ZipFile(out)
        names = zf.namelist()
        assert "output/protocol.md" in names
        assert "output/analysis.py" in names
        assert "output/data.csv" in names

    def test_json_export_bytes_includes_output_files(self, study_with_files):
        from m4.vitrine.export import export_json_bytes

        data = export_json_bytes(study_with_files, study="export-test")
        import io

        zf = zipfile.ZipFile(io.BytesIO(data))
        names = zf.namelist()
        assert "output/protocol.md" in names

    def test_no_files_section_without_output(self, vitrine_dir, tmp_path):
        from m4.vitrine.export import export_html

        mgr = StudyManager(vitrine_dir)
        mgr.get_or_create_study("no-output")
        out = tmp_path / "export.html"
        export_html(mgr, out, study="no-output")
        html = out.read_text()
        assert "Research Files" not in html


# ================================================================
# Public API: register_output_dir from __init__
# ================================================================


class TestPublicRegisterOutputDir:
    def test_register_creates_dir(self, vitrine_dir):
        mgr = StudyManager(vitrine_dir)
        mgr.get_or_create_study("api-test")
        output = mgr.register_output_dir("api-test")
        assert output.exists()
        assert output.is_dir()
