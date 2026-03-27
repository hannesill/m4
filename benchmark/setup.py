"""Set up agent databases and ground truth for benchmark tasks.

Usage:
    python benchmark/setup.py --task mimic-sirs-24h     # one task
    python benchmark/setup.py --all                      # all tasks
    python benchmark/setup.py --all --verify             # setup + sanity check
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure lib/ is importable
sys.path.insert(0, str(Path(__file__).parent))


def verify_ground_truth(task_names: list[str]) -> bool:
    """Verify ground truth by evaluating it against itself (should score 1.0)."""
    from evaluate import evaluate, resolve_ground_truth

    all_ok = True
    for task_name in task_names:
        gt_path = resolve_ground_truth(task_name)
        results = evaluate(task_name, str(gt_path))
        reward = results["reward"]
        status = "OK" if reward == 1.0 else "FAIL"
        print(f"  {task_name}: reward={reward} [{status}]")
        if reward != 1.0:
            all_ok = False
    return all_ok


def main():
    parser = argparse.ArgumentParser(description="Set up benchmark tasks")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--task", help="Task name (e.g., mimic-sirs-24h)")
    group.add_argument("--all", action="store_true", help="Set up all tasks")
    parser.add_argument("--skip-db", action="store_true", help="Skip agent DB creation")
    parser.add_argument(
        "--skip-gt", action="store_true", help="Skip ground truth generation"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify ground truth scores 1.0 against itself (sanity check)",
    )
    args = parser.parse_args()

    from lib.db import list_task_dirs, resolve_task_dir

    if args.all:
        task_dirs = list_task_dirs()
    else:
        try:
            task_dirs = [resolve_task_dir(args.task)]
        except FileNotFoundError as e:
            parser.error(str(e))

    task_names = [p.name for p in task_dirs]

    if not args.skip_db:
        from lib.db import setup_agent_db

        for task_dir in task_dirs:
            print(f"\n--- Setting up agent DB: {task_dir.name} ---")
            setup_agent_db(task_dir)

    if not args.skip_gt:
        from lib.ground_truth import generate

        print("\n--- Generating ground truth ---")
        if args.all:
            generate()
        else:
            generate(args.task)

    if args.verify:
        print("\n--- Verifying ground truth ---")
        if not verify_ground_truth(task_names):
            print("\nWARNING: some tasks did not score 1.0 — check ground truth SQL")
            sys.exit(1)
        print("\nAll ground truth verified.")


if __name__ == "__main__":
    main()
