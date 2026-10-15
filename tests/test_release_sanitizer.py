import importlib.util
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest


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


def test_local_path_redaction_preserves_json_escapes():
    sanitizer = load_sanitizer()
    packager = load_packager()
    inner = json.dumps({"text": "Wrote [output.csv](/var/folders/ab/T/run/output.csv)"})
    text = json.dumps({"agent_result": {"stdout": inner + "\n"}}, indent=2)

    for redacted in (sanitizer.redact_local_paths(text), packager.redact_text(text)):
        outer = json.loads(redacted)
        nested = json.loads(outer["agent_result"]["stdout"])
        assert nested["text"].startswith("Wrote [output.csv](<ANON_TMP_PATH>")
        assert "/var/folders" not in redacted


def test_json_trace_events_redact_tool_output_and_keep_agent_code():
    sanitizer = load_sanitizer()
    config = sanitizer.SanitizerConfig(
        salt=b"test-salt", private_patterns=sanitizer.PrivatePatterns()
    )
    report = sanitizer.FileReport(path="trace.jsonl", action="test", input_size_bytes=0)
    query = "SELECT stay_id, sofa FROM firstday_sofa WHERE stay_id = 30012345"
    events = [
        {
            "type": "assistant",
            "session_id": "12345678-1f2a-4bcd-9ef0-1234567890ab",
            "message": {"content": [{"type": "tool_use", "input": {"command": query}}]},
        },
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "content": "stay_id,sofa\n30012345,4\n30012346,7\n",
                    }
                ]
            },
            "tool_use_result": {
                "stdout": "(30012345, datetime.datetime(2150, 1, 2, 3, 4))"
            },
        },
        {
            "type": "item.completed",
            "item": {"aggregated_output": "30012345 2150-01-02 03:04"},
        },
    ]
    text = "wrapper log line\n" + "".join(json.dumps(event) + "\n" for event in events)

    sanitized = sanitizer.sanitize_text_payload(text, config=config, report=report)
    lines = sanitized.splitlines()
    parsed = [json.loads(line) for line in lines[1:]]

    assert lines[0] == "wrapper log line"
    assert "30012345" not in sanitized
    assert "2150" not in sanitized
    tool_use = parsed[0]["message"]["content"][0]["input"]["command"]
    assert tool_use.startswith(
        "SELECT stay_id, sofa FROM firstday_sofa WHERE stay_id = MIMIC_STAY_"
    )
    assert parsed[0]["session_id"] == "12345678-1f2a-4bcd-9ef0-1234567890ab"
    tool_result = parsed[1]["message"]["content"][0]["content"]
    assert tool_result.startswith("<REDACTED_TOOL_OUTPUT")
    assert parsed[1]["tool_use_result"].startswith("<REDACTED_TOOL_OUTPUT")
    assert parsed[2]["item"]["aggregated_output"].startswith("<REDACTED_TOOL_OUTPUT")
    assert report.redacted_blocks == 3


def test_result_json_stdout_is_sanitized_as_json_events(tmp_path):
    sanitizer = load_sanitizer()
    source = tmp_path / "src"
    output = tmp_path / "out"
    source.mkdir()
    stdout = json.dumps(
        {
            "type": "user",
            "message": {"content": [{"type": "tool_result", "content": "30012345"}]},
        }
    )
    (source / "result.json").write_text(
        json.dumps(
            {"run_id": "run_20260729_105402", "agent_result": {"stdout": stdout + "\n"}}
        )
    )
    config = sanitizer.SanitizerConfig(
        salt=b"test-salt", private_patterns=sanitizer.PrivatePatterns()
    )

    sanitizer.sanitize_tree(source, output, config=config)
    sanitized = json.loads((output / "result.json").read_text())
    event = json.loads(sanitized["agent_result"]["stdout"])

    assert sanitized["run_id"] == "run_20260729_105402"
    assert event["message"]["content"][0]["content"].startswith("<REDACTED_TOOL_OUTPUT")


def write_declared_selection(path, run_dirs):
    rows = ["path"] + [f"benchmark/results/{run}" for run in run_dirs]
    path.write_text("\n".join(rows) + "\n")


def make_run(results_dir, run, artifacts):
    run_dir = results_dir / run
    run_dir.mkdir(parents=True)
    for name in artifacts:
        (run_dir / name).write_text("{}")
    return {"path": str(run_dir)}


def test_packager_selection_rejects_missing_runs_and_artifacts(tmp_path, monkeypatch):
    packager = load_packager()
    results = tmp_path / "results"
    selection = tmp_path / "final_codex_runs.csv"
    write_declared_selection(selection, ["root/run_a", "root/run_b", "root/run_c"])
    monkeypatch.setattr(packager, "RESULTS_DIR", results)
    monkeypatch.setitem(packager.DECLARED_SELECTIONS, "codex_primary", selection)
    rows = [
        make_run(results, "root/run_a", packager.EXPECTED_ARTIFACTS),
        make_run(results, "root/run_b", packager.EXPECTED_ARTIFACTS[:-1]),
    ]

    with pytest.raises(packager.IncompleteEvidenceError) as excinfo:
        packager.verify_selection("codex_primary", rows)
    assert "missing run: root/run_c" in str(excinfo.value)
    assert "missing artifact: root/run_b/egress.jsonl" in str(excinfo.value)

    # An absent results root must fail rather than package zero runs.
    with pytest.raises(packager.IncompleteEvidenceError, match="0 found"):
        packager.verify_selection("codex_primary", [])


def test_packager_selection_accepts_complete_evidence(tmp_path, monkeypatch):
    packager = load_packager()
    results = tmp_path / "results"
    selection = tmp_path / "final_codex_runs.csv"
    write_declared_selection(selection, ["root/run_a"])
    monkeypatch.setattr(packager, "RESULTS_DIR", results)
    monkeypatch.setitem(packager.DECLARED_SELECTIONS, "codex_primary", selection)

    packager.verify_selection(
        "codex_primary", [make_run(results, "root/run_a", packager.EXPECTED_ARTIFACTS)]
    )


@pytest.mark.parametrize(
    "script",
    [
        "make_final_results.py",
        "make_followup_manifest.py",
        "make_followup_tables.py",
        "make_release_metadata.py",
        "make_codex_tables.py",
    ],
)
def test_table_generators_fail_closed_without_runs(tmp_path, script):
    path = (
        Path(__file__).parent.parent
        / "benchmark"
        / "release"
        / "v1"
        / "scripts"
        / script
    )
    results = (tmp_path / "results").resolve()
    paper = tmp_path / "paper"
    results.mkdir()
    env = {
        **os.environ,
        "M4BENCH_RESULTS_DIR": str(results),
        "M4BENCH_PAPER_DIR": str(paper),
    }
    env.pop("M4BENCH_FROZEN_REFERENCE", None)
    env.pop("M4BENCH_M4_DIR", None)

    completed = subprocess.run(
        [sys.executable, str(path)],
        env=env,
        capture_output=True,
        text=True,
    )

    # A public checkout has no run roots; nothing may be written from zero runs.
    assert completed.returncode == 1
    assert "Traceback" not in completed.stderr
    assert f"no runs found under {results}" in completed.stderr
    assert "verify_public_evidence.py" in completed.stderr
    assert not paper.exists()


def load_scanner():
    path = (
        Path(__file__).parent.parent
        / "benchmark"
        / "release"
        / "v1"
        / "scripts"
        / "scan_public_evidence.py"
    )
    spec = importlib.util.spec_from_file_location("scan_public_evidence", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def sanitizer_context(sanitizer, salt=b"test-salt"):
    config = sanitizer.SanitizerConfig(
        salt=salt, private_patterns=sanitizer.PrivatePatterns()
    )
    report = sanitizer.FileReport(path="trace.jsonl", action="test", input_size_bytes=0)
    return config, report


# The review archive lost escape characters before some quotes, so the string
# ends early and the event no longer parses.
MALFORMED_EVENT = (
    '{"type":"item.completed","item":{"command":"bash -lc \\"cat <ANON_LOCAL_PATH>"",'
    '"aggregated_output":"stay_id,age\\n30012345,76\\n"}}\n'
)
FAKE_JWT = "eyJ" + "a" * 20 + ".eyJ" + "b" * 40 + "." + "c" * 30
FAKE_REFRESH_TOKEN = "rt_" + "A1b2" * 20


def test_malformed_event_line_is_withheld_whole():
    sanitizer = load_sanitizer()
    config, report = sanitizer_context(sanitizer)
    with pytest.raises(json.JSONDecodeError):
        json.loads(MALFORMED_EVENT)

    sanitized = sanitizer.sanitize_text_payload(
        MALFORMED_EVENT, config=config, report=report
    )
    event = json.loads(sanitized)

    assert event["type"] == "redacted_unparseable_event"
    assert event["original_type"] == "item.completed"
    assert "30012345" not in sanitized
    assert "76" not in sanitized
    assert report.withheld_unparseable == 1


def test_values_after_escaped_newlines_are_scrubbed():
    sanitizer = load_sanitizer()
    config, report = sanitizer_context(sanitizer)
    # Literal backslash-n: text that is JSON-escaped once more than it was parsed.
    text = (
        "rows:\\n30012345,2150-01-02 03:04:05,F\\n10000032.0\\t"
        "datetime.date(2150, 1, 2)\\n000-12345,2150-1-2\n"
    )

    sanitized = sanitizer.scrub_record_values(text, config=config, report=report)

    for raw in ("30012345", "10000032", "2150", "000-12345"):
        assert raw not in sanitized
    assert "MIMIC_ID_" in sanitized
    assert "EICU_UNIQUE_PID_" in sanitized


def test_credentials_are_redacted_wherever_they_appear():
    sanitizer = load_sanitizer()
    config, report = sanitizer_context(sanitizer)
    account = "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0"
    dump = json.dumps(
        {
            "tokens": {
                "id_token": FAKE_JWT,
                "refresh_token": FAKE_REFRESH_TOKEN,
                "account_id": account,
            }
        }
    )
    event = {
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": "auth.json: " + dump}]},
    }
    # Parsed event, and the same dump on a plain log line with escaped quotes.
    text = json.dumps(event) + "\n" + "log " + json.dumps(dump) + "\n"

    sanitized = sanitizer.sanitize_text_payload(text, config=config, report=report)

    for secret in (FAKE_JWT, FAKE_REFRESH_TOKEN, account):
        assert secret not in sanitized
    assert "<REDACTED_SECRET>" in sanitized
    assert report.redacted_secrets >= 6


def test_result_json_withholds_stdout_fragments_and_unparsed_block(tmp_path):
    sanitizer = load_sanitizer()
    source = tmp_path / "src"
    output = tmp_path / "out"
    source.mkdir()
    event = {
        "type": "user",
        "message": {"content": [{"type": "tool_result", "content": "30012345"}]},
    }
    result = {
        "run_id": "run_a",
        "agent_result": {
            "returncode": 0,
            # A stdout tail starts in the middle of an event.
            "stdout": 'output":"30012345,76\\n","exit_code":0}}\n'
            + json.dumps(event)
            + "\n",
            "unparsed_original_text": '"stdout": "{\\"aggregated_output\\":\\"30012345,76\\"}"',
        },
    }
    (source / "result.json").write_text(json.dumps(result))
    config, _ = sanitizer_context(sanitizer)

    sanitizer.sanitize_tree(source, output, config=config)
    sanitized = json.loads((output / "result.json").read_text())
    agent = sanitized["agent_result"]
    fragment, event_line = agent["stdout"].splitlines()

    assert "30012345" not in json.dumps(sanitized)
    assert agent["returncode"] == 0
    assert fragment.startswith("<REDACTED_EVENT_FRAGMENT ")
    assert json.loads(event_line)["message"]["content"][0]["content"].startswith(
        "<REDACTED_TOOL_OUTPUT"
    )
    assert agent["unparsed_original_text"].startswith(
        "<REDACTED_UNPARSED_AGENT_RESULT "
    )


def test_column_list_without_rows_is_kept(tmp_path):
    sanitizer = load_sanitizer()
    source = tmp_path / "src"
    output = tmp_path / "out"
    source.mkdir()
    instruction = (
        "Required columns:\n"
        "subject_id, stay_id, hadm_id, ab_id, antibiotic_time\n\n"
        "One row per antibiotic.\n"
    )
    (source / "instruction.md").write_text(instruction)
    config, _ = sanitizer_context(sanitizer)

    sanitizer.sanitize_tree(source, output, config=config)

    assert (output / "instruction.md").read_text() == instruction


def test_rows_quoted_in_agent_prose_are_redacted():
    sanitizer = load_sanitizer()
    config, report = sanitizer_context(sanitizer)
    text = (
        "Sample:\n30012345 | 2150-01-02 | 76 | F\n30012346 | 2150-01-03 | 54 | M\n"
        "The patient is a 76-year-old female.\n"
    )
    event = {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "text", "text": text},
                {"type": "tool_use", "input": {"stay_id": 30012345}},
            ]
        },
    }

    sanitized = sanitizer.sanitize_json_line(
        json.dumps(event) + "\n", config=config, report=report
    )
    content = json.loads(sanitized)["message"]["content"]

    assert 'type="identified_rows" lines="2"' in content[0]["text"]
    assert "| F" not in content[0]["text"]
    assert "a <REDACTED_AGE>-year-old female" in content[0]["text"]
    assert content[1]["input"]["stay_id"].startswith("MIMIC_STAY_")


def test_named_id_redaction_keeps_sql_intact():
    sanitizer = load_sanitizer()
    sql = "SELECT c_552 AS stay_id, t1.subject_id FROM x ORDER BY stay_id, 1"

    assert sanitizer.redact_named_ids(sql, b"salt") == sql
    assert "MIMIC_STAY_" in sanitizer.redact_named_ids("stay_id = 30012345", b"salt")
    assert "EICU_UNIT_STAY_" in sanitizer.redact_named_ids(
        "patientunitstayid, 141168", b"salt"
    )


def test_tool_output_placeholder_cannot_be_brute_forced():
    import hashlib

    sanitizer = load_sanitizer()

    first = sanitizer.tool_output_placeholder("42", b"salt-a")
    second = sanitizer.tool_output_placeholder("42", b"salt-b")

    assert first != second
    assert hashlib.sha256(b"42").hexdigest()[:16] not in first


def test_event_with_unicode_line_separator_stays_one_event():
    sanitizer = load_sanitizer()
    line_separator = chr(0x2028)  # str.splitlines would break the event here
    config, report = sanitizer_context(sanitizer)
    event = {
        "type": "user",
        "message": {
            "content": [
                {"type": "tool_result", "content": f"30012345{line_separator} 76"}
            ]
        },
    }
    line = json.dumps(event, ensure_ascii=False) + "\n"

    sanitized = sanitizer.sanitize_text_payload(line, config=config, report=report)

    assert json.loads(sanitized)["message"]["content"][0]["content"].startswith(
        "<REDACTED_TOOL_OUTPUT"
    )
    assert report.withheld_unparseable == 0


def write_leaky_run(run_dir):
    """A run directory holding every leak class the scanner must catch."""
    run_dir.mkdir(parents=True)
    tool_event = {
        "type": "user",
        "message": {
            "content": [{"type": "tool_result", "content": "stay_id\n30012345\n"}]
        },
        "tool_use_result": {"stdout": "30012345"},
    }
    prose_event = {
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "text",
                    "text": "Rows:\n30012345 | 2150-01-02 | 76\n30012346 | 2150-01-03 | 54\n"
                    + json.dumps({"id_token": FAKE_JWT}),
                }
            ]
        },
    }
    (run_dir / "trace.jsonl").write_text(
        "Network locked for benchagent\n"
        + MALFORMED_EVENT
        + json.dumps(tool_event)
        + "\n"
        + json.dumps(prose_event)
        + "\n"
    )
    (run_dir / "result.json").write_text(
        json.dumps(
            {
                "run_id": "run_a",
                "agent_result": {
                    "stdout": 'output":"30012345,76\\n","exit_code":0}}\n'
                    + json.dumps(tool_event)
                    + "\n",
                    "stderr": "",
                    "unparsed_original_text": '"stdout": "\\"30012345,2150-01-02\\""',
                },
            }
        )
    )
    (run_dir / "instruction.md").write_text("subject_id, stay_id, hadm_id\n")


def scan_hits(scanner, root):
    scan = scanner.Scan(dict(scanner.CONTENT))
    for path in sorted(root.rglob("*")):
        if path.is_file():
            scan.file(path, root)
    return {check for check, _ in scan.hits}


def test_scanner_flags_every_known_leak_class(tmp_path):
    scanner = load_scanner()
    write_leaky_run(tmp_path / "runs" / "run_a")
    (tmp_path / "runs" / "run_a" / "output.csv").write_text("stay_id\n30012345\n")

    assert scan_hits(scanner, tmp_path) >= {
        "malformed_event",
        "unredacted_tool_output",
        "unparsed_agent_result",
        "event_fragment",
        "forbidden_file",
        "credential",
        "mimic_identifier",
        "shifted_datetime",
    }


def test_sanitized_run_passes_the_independent_scanner(tmp_path):
    sanitizer = load_sanitizer()
    scanner = load_scanner()
    source = tmp_path / "src"
    output = tmp_path / "out"
    write_leaky_run(source / "runs" / "run_a")
    config, _ = sanitizer_context(sanitizer)

    sanitizer.sanitize_tree(source, output, config=config)

    assert scan_hits(scanner, output) == set()
    # Pseudonymized rows that survive would be caught as well.
    leftover = output / "runs" / "run_a" / "note.md"
    leftover.write_text("MIMIC_ID_0123456789ABCDEF | 76 | F\n")
    assert scan_hits(scanner, output) == {"identified_row"}


def test_wrapped_column_list_is_not_mistaken_for_rows(tmp_path):
    sanitizer = load_sanitizer()
    source = tmp_path / "src"
    output = tmp_path / "out"
    source.mkdir()
    instruction = (
        "Output these exact columns:\n"
        "stay_id, charttime, weight, uo,\n"
        "urineoutput_6hr, urineoutput_12hr, urineoutput_24hr,\n"
        "uo_mlkghr_6hr, uo_tm_6hr, uo_tm_12hr\n"
    )
    (source / "instruction.md").write_text(instruction)
    config, _ = sanitizer_context(sanitizer)

    sanitizer.sanitize_tree(source, output, config=config)

    assert (output / "instruction.md").read_text() == instruction


def test_dash_encoded_host_paths_and_signatures_are_redacted():
    sanitizer = load_sanitizer()
    config, report = sanitizer_context(sanitizer)
    event = {
        "type": "assistant",
        "cwd": "~/.claude/projects/-Users-someone-Developer-m4/session",
        "tmp": "~/.claude/projects/-var-folders-b1-8k0y-T-bench-x",
        "message": {"content": [{"type": "thinking", "signature": "Ep" + "x" * 400}]},
    }

    sanitized = sanitizer.sanitize_json_line(
        json.dumps(event) + "\n", config=config, report=report
    )

    assert "someone" not in sanitized
    assert "8k0y" not in sanitized
    assert json.loads(sanitized)["message"]["content"][0]["signature"] == (
        "<REDACTED_SIGNATURE>"
    )


EICU_PROSE = (
    "Looking at patient 141179:\n"
    "- Patient 315753: minimum GCS=10 at offset 4\n"
    "pid=273710\nrows=con.execute(q)\n"
    "Maximum per component:\n- age: 6\n- gcs: 10\n"
    "# Check row 141194 (gcs_min=12)\n"
    "WHERE patientunitstayid IN (141168, 141178)\n"
    "For patient 141178, the age of 52 maps to a score of 3; gender=F, age=76.\n"
    "Validation passed: `200859` rows, rows: 200859, 5216/546028 matched.\n"
    "Ages 75-80 score 7 points; age >= 16; mean age 62.1.\n"
)


def write_eicu_run(run_dir):
    run_dir.mkdir(parents=True)
    event = {
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": EICU_PROSE}]},
    }
    (run_dir / "trace.jsonl").write_text(json.dumps(event) + "\n")


def test_eicu_stay_ids_and_stated_ages_are_removed(tmp_path):
    sanitizer = load_sanitizer()
    source = tmp_path / "src"
    output = tmp_path / "out"
    write_eicu_run(source / "runs" / "eicu-gcs_no-skill_codex_t1")
    config, _ = sanitizer_context(sanitizer)

    sanitizer.sanitize_tree(source, output, config=config)

    trace = output / "runs" / "eicu-gcs_no-skill_codex_t1" / "trace.jsonl"
    text = json.loads(trace.read_text())["message"]["content"][0]["text"]
    for stay_id in ("141179", "315753", "273710", "141168", "141178", "141194"):
        assert stay_id not in text
    assert text.count("EICU_") == 7
    assert "age of <REDACTED_AGE>" in text
    assert "age=<REDACTED_AGE>" in text
    assert "- age: <REDACTED_AGE>\n- gcs: 10" in text
    # Counts, fractions, age rules, and aggregates are not patient values.
    assert "`200859` rows, rows: 200859, 5216/546028 matched" in text
    assert "Ages 75-80 score 7 points; age >= 16; mean age 62.1." in text


def test_six_digit_codes_outside_eicu_runs_are_kept(tmp_path):
    sanitizer = load_sanitizer()
    source = tmp_path / "src"
    output = tmp_path / "out"
    run = source / "runs" / "mimic-sofa-24h_no-skill_codex_t1"
    run.mkdir(parents=True)
    sql = "SELECT * FROM chartevents WHERE itemid IN (220045, 220050, 223761)"
    event = {
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": sql}]},
    }
    (run / "trace.jsonl").write_text(json.dumps(event) + "\n")
    config, _ = sanitizer_context(sanitizer)

    sanitizer.sanitize_tree(source, output, config=config)

    trace = output / "runs" / run.name / "trace.jsonl"
    assert json.loads(trace.read_text())["message"]["content"][0]["text"] == sql


def test_scanner_flags_eicu_ids_and_ages_and_passes_sanitized_output(tmp_path):
    sanitizer = load_sanitizer()
    scanner = load_scanner()
    source = tmp_path / "src"
    output = tmp_path / "out"
    write_eicu_run(source / "runs" / "eicu-gcs_no-skill_codex_t1")
    config, _ = sanitizer_context(sanitizer)

    assert scan_hits(scanner, source) >= {"eicu_identifier", "patient_age"}

    sanitizer.sanitize_tree(source, output, config=config)

    assert scan_hits(scanner, output) == set()


@pytest.mark.parametrize("row", ["30012345,76", "30012345 | F"])
def test_two_column_rows_quoted_in_agent_prose_are_redacted(tmp_path, row):
    sanitizer = load_sanitizer()
    scanner = load_scanner()
    config, report = sanitizer_context(sanitizer)
    event = {
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": f"Sample:\n{row}\n"}]},
    }

    sanitized = sanitizer.sanitize_json_line(
        json.dumps(event) + "\n", config=config, report=report
    )

    lines = json.loads(sanitized)["message"]["content"][0]["text"].splitlines()
    assert lines[0] == "Sample:"
    assert lines[1].startswith('<REDACTED_DATA_BLOCK type="identified_rows" lines="1"')
    assert len(lines) == 2
    # The scanner catches such a row if it survives with its identifier scrubbed.
    (tmp_path / "note.md").write_text(row.replace("30012345", ID_PSEUDONYM) + "\n")
    assert scan_hits(scanner, tmp_path) == {"identified_row"}


ID_PSEUDONYM = "MIMIC_ID_0123456789ABCDEF"


@pytest.mark.parametrize(
    ("run", "tool_input", "is_identifier"),
    [
        ("mimic-sofa-24h_no-skill_codex_t1", {"ids": [30012345]}, True),
        ("mimic-sofa-24h_no-skill_codex_t1", {"stay_ids": [7]}, True),
        ("mimic-sofa-24h_no-skill_codex_t1", {"itemids": [220045]}, False),
        ("eicu-gcs_no-skill_codex_t1", {"query": {"stays": [141168]}}, True),
        ("eicu-gcs_no-skill_codex_t1", {"timeout": 600000, "limit": 2000}, False),
    ],
)
def test_identifier_numbers_in_tool_input_are_pseudonymized_whatever_their_key(
    tmp_path, run, tool_input, is_identifier
):
    sanitizer = load_sanitizer()
    scanner = load_scanner()
    source = tmp_path / "src"
    output = tmp_path / "out"
    (source / "runs" / run).mkdir(parents=True)
    event = {
        "type": "assistant",
        "message": {"content": [{"type": "tool_use", "input": tool_input}]},
        # Outside tool input, numbers of an identifier's shape are counters.
        "usage": {"input_tokens": 30012345, "cached_input_tokens": 1234567},
    }
    (source / "runs" / run / "trace.jsonl").write_text(json.dumps(event) + "\n")
    config, _ = sanitizer_context(sanitizer)

    assert ("numeric_identifier" in scan_hits(scanner, source)) is is_identifier

    sanitizer.sanitize_tree(source, output, config=config)

    sanitized = json.loads((output / "runs" / run / "trace.jsonl").read_text())
    assert (sanitized["message"]["content"][0]["input"] == tool_input) is not (
        is_identifier
    )
    assert sanitized["usage"] == event["usage"]
    assert scan_hits(scanner, output) == set()


@pytest.mark.parametrize("file_name", ["redactions", "redactions.json"])
def test_scanner_checks_private_regexes_as_well_as_literals(tmp_path, file_name):
    scanner = load_scanner()
    redactions = tmp_path / file_name
    if file_name.endswith(".json"):
        redactions.write_text(
            json.dumps(
                {
                    "literal": ["Project Falcon"],
                    "regex": [{"pattern": "SECRET[0-9]+"}],
                    "allow": ["team@example.org"],
                }
            )
        )
    else:
        redactions.write_text(
            "# private\nliteral: Project Falcon\nregex: SECRET[0-9]+\n"
            "allow: team@example.org\n"
        )
    package = tmp_path / "package"
    package.mkdir()
    (package / "note.md").write_text("Ran SECRET42 for project falcon.\n")

    scan = scanner.Scan(scanner.load_private_patterns(redactions))
    scan.file(package / "note.md", package)

    assert {check for check, _ in scan.hits} == {"private_literal_0", "private_regex_0"}
