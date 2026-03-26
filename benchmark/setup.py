"""Set up agent databases and ground truth for benchmark tasks.

Usage:
    python benchmark/setup.py --task mimic-sirs-24h     # one task
    python benchmark/setup.py --all                      # all tasks
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure lib/ is importable
sys.path.insert(0, str(Path(__file__).parent))

TASKS_DIR = Path("benchmark/tasks")


def main():
    parser = argparse.ArgumentParser(description="Set up benchmark tasks")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--task", help="Task name (e.g., mimic-sirs-24h)")
    group.add_argument("--all", action="store_true", help="Set up all tasks")
    parser.add_argument("--skip-db", action="store_true", help="Skip agent DB creation")
    parser.add_argument(
        "--skip-gt", action="store_true", help="Skip ground truth generation"
    )
    args = parser.parse_args()

    if args.all:
        task_dirs = sorted(p for p in TASKS_DIR.iterdir() if p.is_dir())
    else:
        task_dirs = [TASKS_DIR / args.task]
        if not task_dirs[0].exists():
            parser.error(f"Task directory not found: {task_dirs[0]}")

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


if __name__ == "__main__":
    main()
