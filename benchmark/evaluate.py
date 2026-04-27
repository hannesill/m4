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
GROUND_TRUTH_DIR = BENCHMARK_ROOT / "ground_truth"
METRIC_DECIMALS = 8


def _round_metric(value: float) -> float:
    """Round reported metrics without masking one-row mismatches as perfect."""
    return round(float(value), METRIC_DECIMALS)


def resolve_ground_truth(task_name: str) -> Path:
    """Find the ground truth file for a task."""
    from lib.db import _task_key

    task_key = _task_key(task_name)
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
    try:
        from lib.compare import compare_derived_tables
        from lib.db import load_task_config, resolve_task_dir
        from lib.runner import run_tests

        task_dir = resolve_task_dir(task_name)

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
            col: _round_metric(comparison[col]["match_rate"])
            for col in eval_config["value_columns"]
        }
        test_results["match_rates"] = match_rates
        test_results["reward"] = _round_metric(
            sum(match_rates.values()) / len(match_rates)
        )

        # Surface task-level cohort diagnostics alongside reward. Reward is a
        # recall-style metric (per-column match rate); key_precision tells the
        # reader whether the agent's output cohort is clean or inflated with
        # keys that do not belong. Reward is intentionally unchanged.
        meta = comparison.get("__meta__", {})
        test_results["key_precision"] = _round_metric(meta.get("key_precision", 0.0))
        test_results["extra_keys"] = int(meta.get("extra_keys", 0))
        test_results["agent_unique_keys"] = int(meta.get("agent_unique_keys", 0))

        return test_results
    except Exception as exc:
        return {
            "passed": 0,
            "failed": 0,
            "errors": 1,
            "total": 1,
            "reward": 0.0,
            "match_rates": {},
            "key_precision": 0.0,
            "extra_keys": 0,
            "agent_unique_keys": 0,
            "pytest_output": f"Evaluation failed: {exc}",
            "pytest_stderr": "",
        }


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
    print(
        f"Key precision: {results.get('key_precision', 0.0)} "
        f"({results.get('extra_keys', 0)} extra keys, "
        f"{results.get('agent_unique_keys', 0)} agent keys total)"
    )
    print(f"{'=' * 60}")
    print(f"\n{results['pytest_output']}")


if __name__ == "__main__":
    main()
