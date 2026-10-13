import importlib.util
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).parent.parent / "benchmark" / "release" / "v1" / "scripts"


def load_repair():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "repair_result_json", SCRIPTS / "repair_result_json.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def corrupted_result() -> str:
    """Reproduce the historical corruption: path redaction ate `\\"`."""
    stdout = json.dumps({"text": "Wrote [output.csv](/var/folders/x/T/o.csv)"})
    original = {
        "task": "mimic-sofa-24h",
        "run_id": "run-1",
        "agent_result": {
            "returncode": 0,
            "stdout": stdout + "\n",
            "stderr": "",
            "elapsed_seconds": 12.5,
        },
        "test_results": {"reward": 0.75, "failed": 1, "errors": 0},
        "publishable": True,
    }
    text = json.dumps(original, indent=2)
    # The old pattern stopped at the quote but swallowed the escaping backslash.
    return text.replace("/var/folders/x/T/o.csv)\\", "<ANON_TMP_PATH>")


def test_repair_rebuilds_agent_result_and_keeps_other_fields(tmp_path):
    repair = load_repair()
    text = corrupted_result()
    try:
        json.loads(text)
    except json.JSONDecodeError:
        pass
    else:  # pragma: no cover - guards the fixture itself.
        raise AssertionError("fixture should be malformed")

    members, recovered = repair.repair_text(text)
    derived = json.loads(repair.derived_payload(members))

    assert derived["test_results"] == {"reward": 0.75, "failed": 1, "errors": 0}
    assert derived["publishable"] is True
    assert derived["agent_result"]["returncode"] == 0
    assert derived["agent_result"]["elapsed_seconds"] == 12.5
    assert "<ANON_TMP_PATH>" in derived["agent_result"]["unparsed_original_text"]
    assert recovered == ["elapsed_seconds", "returncode", "stderr"]
    assert derived["derived_repair"]["method"] == repair.REPAIR_METHOD
    assert list(derived)[:3] == ["task", "run_id", "agent_result"]


def test_repair_cli_writes_lineage_and_leaves_valid_files(tmp_path):
    repair = load_repair()
    source = tmp_path / "src"
    (source / "a").mkdir(parents=True)
    (source / "b").mkdir()
    (source / "a" / "result.json").write_text(corrupted_result())
    (source / "b" / "result.json").write_text(json.dumps({"ok": True}))
    lineage_path = tmp_path / "lineage.json"
    sys.argv = [
        "repair_result_json.py",
        str(source),
        "--output-dir",
        str(tmp_path / "out"),
        "--lineage",
        str(lineage_path),
    ]
    repair.main()

    lineage = json.loads(lineage_path.read_text())
    assert lineage["scanned_result_files"] == 2
    assert [r["original_path"] for r in lineage["records"]] == ["a/result.json"]
    record = lineage["records"][0]
    original = (source / "a" / "result.json").read_bytes()
    assert record["original_sha256"] == repair.sha256_bytes(original)
    derived = (tmp_path / "out" / "a" / "result.json").read_bytes()
    assert record["derived_sha256"] == repair.sha256_bytes(derived)
    assert not (tmp_path / "out" / "b").exists()
