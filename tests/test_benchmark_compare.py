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
