from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]


def _load_ground_truth():
    sys.path.insert(0, str(ROOT / "benchmark"))
    spec = importlib.util.spec_from_file_location(
        "lib.ground_truth", ROOT / "benchmark/lib/ground_truth.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["benchmark.lib.ground_truth"] = module
    spec.loader.exec_module(module)
    return module


def test_alias_ground_truth_generates_target_and_manifest(monkeypatch, tmp_path):
    ground_truth = _load_ground_truth()

    db_path = tmp_path / "source.duckdb"
    con = duckdb.connect(str(db_path))
    try:
        con.execute("CREATE TABLE source AS SELECT 1 AS stay_id, 7 AS score")
    finally:
        con.close()

    task_dir = tmp_path / "tasks" / "mimic-score-raw"
    task_dir.mkdir(parents=True)
    gt_dir = tmp_path / "ground_truth"
    gt_dir.mkdir()
    (gt_dir / "score.sql").write_text("SELECT stay_id, score FROM source\n")

    config = {
        "metadata": {"name": "mimic-score-raw"},
        "database": {"source": "mimic-iv"},
        "ground_truth": {"alias": "score"},
        "evaluation": {
            "key_columns": ["stay_id"],
            "value_columns": ["score"],
            "required_columns": ["stay_id", "score"],
        },
    }

    monkeypatch.setattr(ground_truth, "GROUND_TRUTH_DIR", gt_dir)
    monkeypatch.setattr(ground_truth, "SOURCE_DBS", {"mimic-iv": db_path})
    monkeypatch.setattr(ground_truth, "list_task_dirs", lambda: [task_dir])
    monkeypatch.setattr(ground_truth, "resolve_task_dir", lambda _name: task_dir)
    monkeypatch.setattr(ground_truth, "load_task_config", lambda _task_dir: config)

    ground_truth.generate("mimic-score-raw")

    alias_csv = gt_dir / "score.csv.gz"
    raw_csv = gt_dir / "score-raw.csv.gz"
    raw_manifest = json.loads((gt_dir / "score-raw.manifest.json").read_text())

    assert alias_csv.exists()
    assert raw_csv.exists()
    assert raw_manifest["source"] == "alias"
    assert raw_manifest["alias_target"] == "score"
    assert raw_manifest["alias_manifest"]["source"] == "sql"
