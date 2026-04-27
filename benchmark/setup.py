"""Set up agent databases and ground truth for benchmark tasks.

Usage:
    python benchmark/setup.py --task mimic-sirs-24h     # one task
    python benchmark/setup.py --all                      # all tasks
    python benchmark/setup.py --all --verify             # setup + sanity check

    # Contamination analysis schemas
    python benchmark/setup.py --schema obfuscated        # build obfuscated source DB + GT SQL
    python benchmark/setup.py --schema restructured      # build restructured source DB + GT SQL
    python benchmark/setup.py --schema obfuscated --all  # source DB + per-task agent DBs
    python benchmark/setup.py --verify-equivalence       # verify GT matches across conditions
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


def setup_schema(schema_type: str, task_dirs: list[Path] | None = None) -> None:
    """Set up obfuscated or restructured schema: source DB + GT SQL + agent DBs."""
    from lib.transform import (
        DICTIONARY_PATH,
        OBFUSCATED_DB,
        RESTRUCTURED_DB,
        build_dictionary,
        create_obfuscated_db,
        create_restructured_db,
        generate_obfuscated_gt_sql,
        generate_restructured_gt_sql,
        load_dictionary,
        save_dictionary,
        setup_transformed_agent_db,
        verify_dictionary_completeness,
    )

    # Step 1: Dictionary
    if not DICTIONARY_PATH.exists():
        print("\n--- Building dictionary ---")
        d = build_dictionary()
        save_dictionary(d)
        verify_dictionary_completeness(dictionary=d)
    else:
        d = load_dictionary()
        print(f"Using existing dictionary: {DICTIONARY_PATH}")

    # Step 2: Source DB
    if schema_type == "obfuscated":
        if not OBFUSCATED_DB.exists():
            print("\n--- Creating obfuscated source DB ---")
            create_obfuscated_db(dictionary=d)
        else:
            print(f"Using existing obfuscated DB: {OBFUSCATED_DB}")

        print("\n--- Generating obfuscated GT SQL ---")
        generate_obfuscated_gt_sql(d)

    elif schema_type == "restructured":
        # Restructured depends on obfuscated
        if not OBFUSCATED_DB.exists():
            print("\n--- Creating obfuscated source DB (prerequisite) ---")
            create_obfuscated_db(dictionary=d)

        if not RESTRUCTURED_DB.exists():
            print("\n--- Creating restructured source DB ---")
            create_restructured_db(dictionary=d)
        else:
            print(f"Using existing restructured DB: {RESTRUCTURED_DB}")

        print("\n--- Generating obfuscated GT SQL ---")
        generate_obfuscated_gt_sql(d)
        print("\n--- Generating restructured GT SQL ---")
        generate_restructured_gt_sql(d)

    # Step 3: Per-task agent DBs (if task_dirs provided)
    if task_dirs:
        print(f"\n--- Setting up {schema_type} agent DBs ---")
        for task_dir in task_dirs:
            print(f"\n  {task_dir.name}:")
            setup_transformed_agent_db(task_dir, schema_type, d)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description="Set up benchmark tasks")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--task", help="Task name (e.g., mimic-sirs-24h)")
    group.add_argument("--all", action="store_true", help="Set up all tasks")
    parser.add_argument(
        "--schema",
        choices=["obfuscated", "restructured"],
        help="Set up contamination analysis schema (source DB + GT SQL)",
    )
    parser.add_argument(
        "--verify-equivalence",
        action="store_true",
        help="Verify GT matches across native/obfuscated/restructured",
    )
    parser.add_argument("--skip-db", action="store_true", help="Skip agent DB creation")
    parser.add_argument(
        "--skip-gt", action="store_true", help="Skip ground truth generation"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify ground truth scores 1.0 against itself (sanity check)",
    )
    return parser


def _resolve_task_dirs(args, parser: argparse.ArgumentParser) -> list[Path] | None:
    """Resolve task selection for standard or transformed setup."""
    from lib.db import list_task_dirs, resolve_task_dir

    if args.all:
        return list_task_dirs()
    if args.task:
        try:
            return [resolve_task_dir(args.task)]
        except FileNotFoundError as e:
            parser.error(str(e))
    return None


def main():
    parser = build_parser()
    args = parser.parse_args()

    # Handle schema setup
    if args.schema:
        task_dirs = _resolve_task_dirs(args, parser)
        setup_schema(args.schema, task_dirs)
        return

    # Handle equivalence verification
    if args.verify_equivalence:
        if args.task or args.all:
            parser.error("--verify-equivalence cannot be combined with --task/--all")
        from lib.db import _task_key, list_task_dirs, load_task_config
        from lib.transform import load_dictionary, verify_gt_equivalence

        d = load_dictionary()
        gt_dir = Path(__file__).resolve().parent / "ground_truth"
        mimic_gt_keys: set[str] = set()
        for task_dir in list_task_dirs():
            config = load_task_config(task_dir)
            if config.get("database", {}).get("source", "mimic-iv") != "mimic-iv":
                continue
            task_name = config["metadata"]["name"]
            task_key = _task_key(task_name)
            mimic_gt_keys.add(config.get("ground_truth", {}).get("alias", task_key))

        all_ok = True
        for sql_file in sorted(gt_dir.glob("*.sql")):
            task_key = sql_file.stem
            if task_key not in mimic_gt_keys:
                print(f"  {task_key}: skipped (no MIMIC-IV transformed task)")
                continue
            ok = verify_gt_equivalence(task_key, dictionary=d)
            if not ok:
                all_ok = False
        if all_ok:
            print("\nAll GT equivalence checks passed.")
        else:
            print("\nSome GT equivalence checks FAILED.")
            sys.exit(1)
        return

    # Standard setup
    task_dirs = _resolve_task_dirs(args, parser)
    if not task_dirs:
        parser.error(
            "one of --task, --all, --schema, or --verify-equivalence is required"
        )

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
