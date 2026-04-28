"""Generic task evaluation tests.

Reads task configuration from TASK_DIR environment variable.
Reads output and ground truth paths from AGENT_OUTPUT_PATH and GROUND_TRUTH_PATH.

Usage (called by the harness or evaluate.py):
    TASK_DIR=benchmark/tasks/mimic-sirs-24h \
    AGENT_OUTPUT_PATH=output.csv \
    GROUND_TRUTH_PATH=benchmark/ground_truth/sirs-24h.csv.gz \
    python -m pytest benchmark/lib/test_task.py -v
"""

import os
import sys
from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

# Ensure benchmark/lib is importable
sys.path.insert(0, str(Path(__file__).parent))
from compare import compare_derived_tables, read_benchmark_csv, scored_value_columns

# --- Load task config ---

TASK_DIR = os.environ.get("TASK_DIR", "")
assert TASK_DIR, "TASK_DIR environment variable not set"

with open(Path(TASK_DIR) / "task.toml", "rb") as _f:
    _config = tomllib.load(_f)

_eval = _config["evaluation"]
KEY_COLUMNS = _eval["key_columns"]
VALUE_COLUMNS = _eval["value_columns"]
SCORE_COLUMNS = scored_value_columns(_eval)
REQUIRED_COLUMNS = _eval.get("required_columns", KEY_COLUMNS + VALUE_COLUMNS)
ROW_COVERAGE_THRESHOLD = _eval.get("row_coverage_threshold", 0.95)
ACCURACY_THRESHOLD = _eval.get("accuracy_threshold", 0.90)
TOLERANCE = _eval.get("tolerance", {})

# --- Paths ---

GROUND_TRUTH = os.environ.get("GROUND_TRUTH_PATH", "")
AGENT_OUTPUT = os.environ.get("AGENT_OUTPUT_PATH", "")


# --- Tests ---


def test_output_exists():
    assert AGENT_OUTPUT, "AGENT_OUTPUT_PATH environment variable not set"
    assert os.path.exists(AGENT_OUTPUT), f"Output file not found: {AGENT_OUTPUT}"


def test_output_is_valid_csv():
    df = read_benchmark_csv(AGENT_OUTPUT)
    assert len(df) > 0, "Output CSV is empty"


def test_has_required_columns():
    df = read_benchmark_csv(AGENT_OUTPUT)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    assert not missing, f"Missing columns: {missing}. Got: {list(df.columns)}"


def test_row_coverage():
    """Agent should produce matching keys for at least the configured coverage threshold."""
    agent = read_benchmark_csv(AGENT_OUTPUT)
    truth = read_benchmark_csv(GROUND_TRUTH)
    matched_keys = truth.merge(
        agent[KEY_COLUMNS].drop_duplicates(), on=KEY_COLUMNS, how="inner"
    )
    coverage = len(matched_keys) / len(truth)
    assert coverage >= ROW_COVERAGE_THRESHOLD, (
        f"Only {coverage:.1%} of ground truth keys matched "
        f"({len(matched_keys)}/{len(truth)}). "
        f"Need >= {ROW_COVERAGE_THRESHOLD:.0%}."
    )


@pytest.mark.parametrize("column", SCORE_COLUMNS)
def test_score_accuracy(column):
    """Each value column should match ground truth at the configured threshold."""
    results = compare_derived_tables(
        AGENT_OUTPUT,
        GROUND_TRUTH,
        key_columns=KEY_COLUMNS,
        value_columns=[column],
        tolerance=TOLERANCE,
    )
    rate = results[column]["match_rate"]
    assert rate >= ACCURACY_THRESHOLD, (
        f"{column}: {rate:.1%} match rate "
        f"({results[column]['matched']}/{results[column]['total']}). "
        f"Need >= {ACCURACY_THRESHOLD:.0%}. "
        f"Examples: {results[column]['mismatched_examples']}"
    )
