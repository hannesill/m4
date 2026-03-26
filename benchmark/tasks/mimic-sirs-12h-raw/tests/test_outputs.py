"""Tests for SIRS task output validation.

Compares agent-produced SIRS scores against MIT-LCP mimic-code ground truth.
Paths are configured via environment variables:
  AGENT_OUTPUT_PATH: path to agent's output CSV
  GROUND_TRUTH_PATH: path to ground truth CSV
"""

import os
import sys

import pandas as pd
import pytest

# Add shared utilities to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "shared"))
from test_utils import compare_derived_tables

GROUND_TRUTH = os.environ.get(
    "GROUND_TRUTH_PATH",
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "..",
        "shared",
        "ground_truth",
        "sirs.csv.gz",
    ),
)
AGENT_OUTPUT = os.environ.get("AGENT_OUTPUT_PATH", "")

REQUIRED_COLUMNS = [
    "subject_id",
    "hadm_id",
    "stay_id",
    "sirs",
    "temp_score",
    "heart_rate_score",
    "resp_score",
    "wbc_score",
]


def test_output_exists():
    assert AGENT_OUTPUT, "AGENT_OUTPUT_PATH environment variable not set"
    assert os.path.exists(AGENT_OUTPUT), f"Output file not found: {AGENT_OUTPUT}"


def test_output_is_valid_csv():
    df = pd.read_csv(AGENT_OUTPUT)
    assert len(df) > 0, "Output CSV is empty"


def test_has_required_columns():
    df = pd.read_csv(AGENT_OUTPUT)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    assert not missing, f"Missing columns: {missing}. Got: {list(df.columns)}"


def test_row_coverage():
    """Agent should produce output for at least 95% of ICU stays."""
    agent = pd.read_csv(AGENT_OUTPUT)
    truth = pd.read_csv(GROUND_TRUTH)
    coverage = len(agent) / len(truth)
    assert coverage >= 0.95, (
        f"Only {coverage:.1%} of ICU stays covered ({len(agent)}/{len(truth)}). Need >= 95%."
    )


@pytest.mark.parametrize(
    "column",
    [
        "sirs",
        "temp_score",
        "heart_rate_score",
        "resp_score",
        "wbc_score",
    ],
)
def test_score_accuracy(column):
    """Each score column should match ground truth on >= 90% of rows."""
    results = compare_derived_tables(
        AGENT_OUTPUT,
        GROUND_TRUTH,
        key_columns=["stay_id"],
        value_columns=[column],
    )
    rate = results[column]["match_rate"]
    assert rate >= 0.90, (
        f"{column}: {rate:.1%} match rate ({results[column]['matched']}/{results[column]['total']}). "
        f"Need >= 90%. Examples of mismatches: {results[column]['mismatched_examples']}"
    )
