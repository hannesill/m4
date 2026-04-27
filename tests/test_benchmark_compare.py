from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def _load_compare():
    spec = importlib.util.spec_from_file_location(
        "benchmark_compare", ROOT / "benchmark/lib/compare.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["benchmark_compare"] = module
    spec.loader.exec_module(module)
    return module


def _load_evaluate():
    spec = importlib.util.spec_from_file_location(
        "benchmark_evaluate", ROOT / "benchmark/evaluate.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["benchmark_evaluate"] = module
    spec.loader.exec_module(module)
    return module


def _write_csv(path: Path, rows: list[dict]) -> None:
    pd.DataFrame(rows).to_csv(path, index=False)


def test_compare_penalizes_extra_agent_keys(tmp_path):
    compare = _load_compare()
    truth = tmp_path / "truth.csv"
    agent = tmp_path / "agent.csv"
    _write_csv(truth, [{"stay_id": 1, "score": 4}, {"stay_id": 2, "score": 5}])
    _write_csv(
        agent,
        [
            {"stay_id": 1, "score": 4},
            {"stay_id": 2, "score": 5},
            {"stay_id": 3, "score": 99},
        ],
    )

    result = compare.compare_derived_tables(
        str(agent), str(truth), key_columns=["stay_id"], value_columns=["score"]
    )

    assert result["score"]["matched"] == 2
    assert result["score"]["total"] == 3
    assert result["score"]["extra_rows"] == 1
    assert result["score"]["match_rate"] == 2 / 3


def test_compare_penalizes_duplicate_agent_keys(tmp_path):
    compare = _load_compare()
    truth = tmp_path / "truth.csv"
    agent = tmp_path / "agent.csv"
    _write_csv(truth, [{"stay_id": 1, "score": 4}, {"stay_id": 2, "score": 5}])
    _write_csv(
        agent,
        [
            {"stay_id": 1, "score": 4},
            {"stay_id": 1, "score": 4},
            {"stay_id": 2, "score": 5},
        ],
    )

    result = compare.compare_derived_tables(
        str(agent), str(truth), key_columns=["stay_id"], value_columns=["score"]
    )

    assert result["score"]["matched"] == 2
    assert result["score"]["total"] == 3
    assert result["score"]["agent_duplicates"] == 1
    assert result["score"]["match_rate"] == 2 / 3


def test_compare_missing_null_truth_key_is_not_a_match(tmp_path):
    compare = _load_compare()
    truth = tmp_path / "truth.csv"
    agent = tmp_path / "agent.csv"
    _write_csv(truth, [{"stay_id": 1, "score": None}, {"stay_id": 2, "score": 5}])
    _write_csv(agent, [{"stay_id": 2, "score": 5}])

    result = compare.compare_derived_tables(
        str(agent), str(truth), key_columns=["stay_id"], value_columns=["score"]
    )

    assert result["score"]["matched"] == 1
    assert result["score"]["missing_rows"] == 1
    assert result["score"]["match_rate"] == 0.5


def test_scored_value_columns_excludes_required_metadata():
    compare = _load_compare()

    score_columns = compare.scored_value_columns(
        {
            "key_columns": ["stay_id"],
            "value_columns": ["meld"],
            "required_columns": ["subject_id", "hadm_id", "stay_id", "meld"],
        }
    )

    assert score_columns == ["meld"]


def test_compare_numeric_tolerance_handles_nullable_truth(tmp_path):
    compare = _load_compare()
    truth = tmp_path / "truth.csv"
    agent = tmp_path / "agent.csv"
    _write_csv(
        truth,
        [
            {"stay_id": 1, "scr_baseline": 1.0},
            {"stay_id": 2, "scr_baseline": None},
        ],
    )
    _write_csv(
        agent,
        [
            {"stay_id": 1, "scr_baseline": 1.04},
            {"stay_id": 2, "scr_baseline": None},
        ],
    )

    result = compare.compare_derived_tables(
        str(agent),
        str(truth),
        key_columns=["stay_id"],
        value_columns=["scr_baseline"],
        tolerance={"scr_baseline": 0.05},
    )

    assert result["scr_baseline"]["matched"] == 2
    assert result["scr_baseline"]["match_rate"] == 1.0


def test_metric_rounding_preserves_near_perfect_mismatch():
    evaluate = _load_evaluate()

    rounded = evaluate._round_metric(200858 / 200859)

    assert rounded == 0.99999502
    assert rounded < 1.0
