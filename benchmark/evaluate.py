"""Standalone evaluation: check an output CSV against a task's ground truth.

Usage:
    python benchmark/evaluate.py --task mimic-sirs-24h --output path/to/output.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure lib/ is importable
sys.path.insert(0, str(Path(__file__).parent))

BENCHMARK_ROOT = Path(__file__).parent
TASKS_DIR = BENCHMARK_ROOT / "tasks"
GROUND_TRUTH_DIR = BENCHMARK_ROOT / "ground_truth"


def resolve_ground_truth(task_name: str) -> Path:
    """Find the ground truth file for a task."""
    task_key = task_name.replace("mimic-", "")
    gt_gz = GROUND_TRUTH_DIR / f"{task_key}.csv.gz"
    gt_csv = GROUND_TRUTH_DIR / f"{task_key}.csv"
    if gt_gz.exists():
        return gt_gz
    if gt_csv.exists():
        return gt_csv
    raise FileNotFoundError(
        f"Ground truth not found for {task_name}. "
        f"Run: python benchmark/setup.py --task {task_name}"
    )


def evaluate(task_name: str, output_path: str) -> dict:
    """Run evaluation tests and return results.

    Reward is the mean per-column match rate (continuous, 0.0-1.0),
    computed directly from comparing agent output to ground truth.
    Pytest tests are kept for pass/fail diagnostics.
    """
    from lib.compare import compare_derived_tables
    from lib.db import load_task_config
    from lib.runner import run_tests

    task_dir = TASKS_DIR / task_name
    if not task_dir.exists():
        raise FileNotFoundError(f"Task not found: {task_dir}")

    gt_path = resolve_ground_truth(task_name)
    test_results = run_tests(task_dir, output_path, gt_path)

    # Compute continuous reward from raw match rates
    config = load_task_config(task_dir)
    eval_config = config["evaluation"]
    comparison = compare_derived_tables(
        output_path,
        str(gt_path),
        key_columns=eval_config["key_columns"],
        value_columns=eval_config["value_columns"],
        tolerance=eval_config.get("tolerance", {}),
    )
    match_rates = {
        col: round(comparison[col]["match_rate"], 4)
        for col in eval_config["value_columns"]
    }
    test_results["match_rates"] = match_rates
    test_results["reward"] = round(sum(match_rates.values()) / len(match_rates), 4)

    return test_results


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate agent output against ground truth"
    )
    parser.add_argument(
        "--task", required=True, help="Task name (e.g., mimic-sirs-24h)"
    )
    parser.add_argument("--output", required=True, help="Path to agent's output CSV")
    args = parser.parse_args()

    results = evaluate(args.task, args.output)

    print(f"\n{'=' * 60}")
    print(f"Evaluation: {args.task}")
    print(f"Output: {args.output}")
    print(f"Results: {results['passed']}/{results['total']} tests passed")
    print(f"Reward: {results['reward']}")
    print(f"{'=' * 60}")
    print(f"\n{results['pytest_output']}")


if __name__ == "__main__":
    main()
