import importlib.util
import json
import sys
import tarfile
from pathlib import Path


def load_sanitizer():
    path = (
        Path(__file__).parent.parent
        / "benchmark"
        / "release"
        / "v1"
        / "scripts"
        / "sanitize_artifacts.py"
    )
    spec = importlib.util.spec_from_file_location("sanitize_artifacts", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_packager():
    path = (
        Path(__file__).parent.parent
        / "benchmark"
        / "release"
        / "v1"
        / "scripts"
        / "package_review_artifact.py"
    )
    scripts_dir = str(path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location("package_review_artifact", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_csv_default_keeps_scores_only(tmp_path):
    sanitizer = load_sanitizer()
    source = tmp_path / "src"
    output = tmp_path / "out"
    source.mkdir()
    (source / "output.csv").write_text(
        "subject_id,hadm_id,stay_id,charttime,gender,age,sofa,respiration\n"
        "100,200,300,2150-01-01 00:00:00,F,65,4,1\n"
        "100,200,300,2150-01-01 06:30:00,F,65,5,2\n"
    )

    config = sanitizer.SanitizerConfig(
        salt=b"test-salt",
        private_patterns=sanitizer.PrivatePatterns(),
    )
    report = sanitizer.sanitize_tree(source, output, config=config)

    sanitized = (output / "output.csv").read_text()
    header = sanitized.splitlines()[0]
    assert header == "row_id,sofa,respiration"
    assert "100" not in sanitized
    assert "200" not in sanitized
    assert "300" not in sanitized
    assert "2150-01-01" not in sanitized
    assert "F" not in sanitized
    assert "65" not in sanitized
    assert "row_000001" in sanitized
    assert "row_000002" in sanitized
    assert ",4" in sanitized
    assert ",5" in sanitized
    assert report.to_json()["summary"]["csv_rows_processed"] == 2
    assert "subject_id" in report.files[0].dropped_columns


def test_csv_pseudonymized_full_mode_keeps_all_columns_with_transforms(tmp_path):
    sanitizer = load_sanitizer()
    source = tmp_path / "src"
    output = tmp_path / "out"
    source.mkdir()
    (source / "output.csv").write_text(
        "subject_id,hadm_id,stay_id,charttime,sofa\n"
        "100,200,300,2150-01-01 00:00:00,4\n"
        "100,200,300,2150-01-01 06:30:00,5\n"
    )

    config = sanitizer.SanitizerConfig(
        salt=b"test-salt",
        private_patterns=sanitizer.PrivatePatterns(),
        csv_mode="pseudonymized-full",
    )
    sanitizer.sanitize_tree(source, output, config=config)

    sanitized = (output / "output.csv").read_text()
    assert "MIMIC_SUBJECT_" in sanitized
    assert "MIMIC_HADM_" in sanitized
    assert "MIMIC_STAY_" in sanitized
    assert "+0.000h" in sanitized
    assert "+6.500h" in sanitized


def test_scores_only_can_include_private_row_key_hash(tmp_path):
    sanitizer = load_sanitizer()
    source = tmp_path / "src"
    output = tmp_path / "out"
    source.mkdir()
    (source / "output.csv").write_text("stay_id,sofa\n300,4\n")

    config = sanitizer.SanitizerConfig(
        salt=b"test-salt",
        private_patterns=sanitizer.PrivatePatterns(),
        include_row_key_hash=True,
    )
    sanitizer.sanitize_tree(source, output, config=config)

    sanitized = (output / "output.csv").read_text()
    assert sanitized.splitlines()[0] == "row_id,row_key_hash,sofa"
    assert "ROWKEY_" in sanitized
    assert "300" not in sanitized


def test_scores_only_does_not_project_metadata_csv(tmp_path):
    sanitizer = load_sanitizer()
    source = tmp_path / "src"
    output = tmp_path / "out"
    source.mkdir()
    (source / "final_codex_runs.csv").write_text(
        "run_id,path,subject_id,reward\nrun_a,/Users/example/results,100,0.75\n"
    )

    config = sanitizer.SanitizerConfig(
        salt=b"test-salt",
        private_patterns=sanitizer.PrivatePatterns(),
    )
    sanitizer.sanitize_tree(source, output, config=config)

    sanitized = (output / "final_codex_runs.csv").read_text()
    assert sanitized.splitlines()[0] == "run_id,path,subject_id,reward"
    assert "row_id" not in sanitized.splitlines()[0]
    assert "<ANON_LOCAL_PATH>" in sanitized
    assert "MIMIC_SUBJECT_" in sanitized
    assert "100" not in sanitized


def test_trace_redacts_private_terms_emails_and_data_blocks(tmp_path):
    sanitizer = load_sanitizer()
    source = tmp_path / "src"
    output = tmp_path / "out"
    source.mkdir()
    (source / "trace.jsonl").write_text(
        "Ran by Jane Reviewer at jane@example.edu\n"
        "subject_id,stay_id,charttime,sofa\n"
        "100,300,2150-01-01 00:00:00,4\n"
        "101,301,2150-01-02 00:00:00,2\n"
        "subject_id=100 remained in a small snippet\n"
    )
    patterns = sanitizer.PrivatePatterns(literals=["Jane Reviewer"])
    config = sanitizer.SanitizerConfig(salt=b"test-salt", private_patterns=patterns)

    sanitizer.sanitize_tree(source, output, config=config)
    sanitized = (output / "trace.jsonl").read_text()

    assert "Jane Reviewer" not in sanitized
    assert "jane@example.edu" not in sanitized
    assert "<REDACTED_EMAIL>" in sanitized
    assert "<REDACTED_DATA_BLOCK" in sanitized
    assert "2150-01-01" not in sanitized
    assert "subject_id=100" not in sanitized
    assert "MIMIC_SUBJECT_" in sanitized


def test_trace_keeps_sql_column_provenance(tmp_path):
    sanitizer = load_sanitizer()
    source = tmp_path / "src"
    output = tmp_path / "out"
    source.mkdir()
    (source / "trace.jsonl").write_text(
        "SELECT subject_id, stay_id, charttime, sofa FROM firstday_sofa\n"
    )
    config = sanitizer.SanitizerConfig(
        salt=b"test-salt",
        private_patterns=sanitizer.PrivatePatterns(),
    )

    sanitizer.sanitize_tree(source, output, config=config)
    sanitized = (output / "trace.jsonl").read_text()

    assert "SELECT subject_id, stay_id, charttime, sofa" in sanitized
    assert "<REDACTED_DATA_BLOCK" not in sanitized


def test_report_does_not_publish_private_patterns(tmp_path):
    sanitizer = load_sanitizer()
    source = tmp_path / "src"
    output = tmp_path / "out"
    source.mkdir()
    (source / "result.json").write_text(
        json.dumps({"agent_result": {"stdout": "Secret Name x@y.edu"}})
    )
    config = sanitizer.SanitizerConfig(
        salt=b"test-salt",
        private_patterns=sanitizer.PrivatePatterns(literals=["Secret Name"]),
    )

    sanitizer.sanitize_tree(source, output, config=config)
    report = json.loads((output / "SANITIZATION_REPORT.json").read_text())
    report_text = json.dumps(report)

    assert report["private_redaction_patterns"]["loaded"] is True
    assert report["private_redaction_patterns"]["literal_count"] == 1
    assert "Secret Name" not in report_text
    assert str(source) not in report_text
    assert str(output) not in report_text
    assert "input_sha256" not in report_text


def test_private_report_details_are_opt_in(tmp_path):
    sanitizer = load_sanitizer()
    source = tmp_path / "src"
    output = tmp_path / "out"
    source.mkdir()
    (source / "result.json").write_text("{}")
    config = sanitizer.SanitizerConfig(
        salt=b"test-salt",
        private_patterns=sanitizer.PrivatePatterns(),
    )

    sanitizer.sanitize_tree(
        source,
        output,
        config=config,
        include_private_report_details=True,
    )
    report = json.loads((output / "SANITIZATION_REPORT.json").read_text())
    report_text = json.dumps(report)

    assert str(source) in report_text
    assert str(output) in report_text
    assert "input_sha256" in report_text


def test_metadata_json_redacts_source_hash_fields(tmp_path):
    sanitizer = load_sanitizer()
    source = tmp_path / "src"
    output = tmp_path / "out"
    source.mkdir()
    (source / "artifact_hash_manifest.json").write_text(
        json.dumps(
            {
                "relative_path": "run/output.csv",
                "sha256": "a" * 64,
                "input_sha256": "b" * 64,
            }
        )
    )
    config = sanitizer.SanitizerConfig(
        salt=b"test-salt",
        private_patterns=sanitizer.PrivatePatterns(),
    )

    sanitizer.sanitize_tree(source, output, config=config)
    sanitized = json.loads((output / "artifact_hash_manifest.json").read_text())

    assert sanitized["sha256"] == "<REDACTED_SOURCE_HASH>"
    assert sanitized["input_sha256"] == "<REDACTED_SOURCE_HASH>"


def test_packager_add_file_uses_public_sanitizer(tmp_path):
    packager = load_packager()
    sanitizer = load_sanitizer()
    source = tmp_path / "output.csv"
    source.write_text(
        "subject_id,stay_id,charttime,gender,age,sofa\n"
        "100,300,2150-01-01 00:00:00,F,65,4\n"
    )
    config = sanitizer.SanitizerConfig(
        salt=b"test-salt",
        private_patterns=sanitizer.PrivatePatterns(),
    )
    report = sanitizer.SanitizationReport(source="src", output="out")
    tar_path = tmp_path / "artifact.tar"

    with tarfile.open(tar_path, "w") as tar:
        packager.add_file(
            tar,
            source,
            Path("m4bench-review-artifact/runs/example/output.csv"),
            rel_path=Path("runs/example/output.csv"),
            sanitizer_config=config,
            sanitization_report=report,
            dry_run=False,
        )

    with tarfile.open(tar_path, "r") as tar:
        member = tar.extractfile("m4bench-review-artifact/runs/example/output.csv")
        assert member is not None
        payload = member.read().decode()

    assert payload.splitlines()[0] == "row_id,sofa"
    assert "subject_id" not in payload
    assert "2150" not in payload
    assert "row_000001,4" in payload
    assert report.files[0].dropped_columns == [
        "subject_id",
        "stay_id",
        "charttime",
        "gender",
        "age",
    ]
