"""ClinSkillsBench evaluation harness.

Orchestrates: task setup → agent invocation → output collection → test execution.

Usage:
    # Run SIRS task with Claude Code, with-skill condition
    python benchmark/harness/run.py --task mimic-sirs --condition with-skill --agent claude

    # Run without skill
    python benchmark/harness/run.py --task mimic-sirs --condition no-skill --agent claude

    # Run with self-generated skill
    python benchmark/harness/run.py --task mimic-sirs --condition self-generated --agent claude

    # Specify model (for claude)
    python benchmark/harness/run.py --task mimic-sirs --condition with-skill --agent claude --model opus

    # Just run the oracle solution and tests (no agent)
    python benchmark/harness/run.py --task mimic-sirs --oracle
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BENCHMARK_ROOT = Path(__file__).parent.parent
TASKS_DIR = BENCHMARK_ROOT / "tasks"
GROUND_TRUTH_DIR = BENCHMARK_ROOT / "shared" / "ground_truth"
AGENT_DB_DIR = BENCHMARK_ROOT / "agent_db"
RESULTS_DIR = BENCHMARK_ROOT / "results"

SELF_GEN_PROMPT = """

Before solving this task, take a moment to create your own procedural skill document.
Analyze the requirements, then:
1. Write 1-3 modular skill documents as markdown files in your working directory
2. Each skill should contain step-by-step procedures, not just facts
3. Then use those skills to solve the task
"""

# Agent CLI commands
AGENT_COMMANDS = {
    "claude": {
        "cmd": [
            "claude",
            "-p",
            "--allowedTools",
            "Bash(*),Read,Write,Glob,Grep,Edit",
        ],
        "skill_paths": [
            "{home}/.claude/skills",
        ],
    },
    "codex": {
        "cmd": ["codex", "--quiet", "--approval-mode", "full-auto"],
        "skill_paths": [
            "{home}/.codex/skills",
        ],
    },
    "gemini": {
        "cmd": ["gemini", "-p"],
        "skill_paths": [
            "{home}/.gemini/skills",
        ],
    },
}


def load_task_config(task_name: str) -> dict:
    """Load task.toml configuration."""
    import tomllib

    task_dir = TASKS_DIR / task_name
    config_path = task_dir / "task.toml"
    if not config_path.exists():
        raise FileNotFoundError(f"Task config not found: {config_path}")
    with open(config_path, "rb") as f:
        return tomllib.load(f)


def _resolve_agent_db(task_name: str) -> str:
    """Find the agent DB for a task. Task-specific DB takes priority."""
    task_key = task_name.replace("mimic-", "")
    task_db = AGENT_DB_DIR / f"mimic_iv_{task_key}.duckdb"
    generic_db = AGENT_DB_DIR / "mimic_iv.duckdb"
    return str(task_db if task_db.exists() else generic_db)


def setup_workdir(task_name: str, workdir: Path) -> None:
    """Prepare the agent's working directory with symlinked data."""
    # Symlink agent DB into workdir so agent only needs local access
    agent_db_src = Path(_resolve_agent_db(task_name)).resolve()
    agent_db_link = workdir / "database.duckdb"
    if not agent_db_link.exists():
        agent_db_link.symlink_to(agent_db_src)


def prepare_instruction(task_name: str, workdir: Path, condition: str) -> str:
    """Load instruction.md and fill in paths."""
    task_dir = TASKS_DIR / task_name
    instruction = (task_dir / "instruction.md").read_text()

    # Use relative paths so agent stays in workdir
    db_path = "./database.duckdb"
    output_path = "./output.csv"

    instruction = instruction.replace("{db_path}", db_path)
    instruction = instruction.replace("{output_path}", output_path)

    if condition == "self-generated":
        instruction += SELF_GEN_PROMPT

    return instruction


def inject_skill(task_name: str, agent_name: str) -> list[Path]:
    """Copy skill files to agent's skill discovery path. Returns paths for cleanup."""
    task_dir = TASKS_DIR / task_name
    skills_dir = task_dir / "skills"

    if not skills_dir.exists():
        return []

    agent_config = AGENT_COMMANDS.get(agent_name, {})
    home = str(Path.home())
    created_paths = []

    for skill_path_template in agent_config.get("skill_paths", []):
        target_base = Path(skill_path_template.format(home=home))

        for skill_dir in skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            target = target_base / skill_dir.name
            if target.exists():
                # Don't overwrite existing skills
                continue
            shutil.copytree(skill_dir, target)
            created_paths.append(target)
            print(f"  Injected skill: {target}")

    return created_paths


def cleanup_skills(paths: list[Path]) -> None:
    """Remove injected skill directories."""
    for p in paths:
        if p.exists():
            shutil.rmtree(p)
            print(f"  Cleaned up skill: {p}")


def run_agent(
    instruction: str,
    agent_name: str,
    workdir: Path,
    model: str | None = None,
    verbose: bool = False,
) -> dict:
    """Invoke an agent CLI with the instruction. Returns result dict."""
    agent_config = AGENT_COMMANDS.get(agent_name)
    if not agent_config:
        raise ValueError(
            f"Unknown agent: {agent_name}. Available: {list(AGENT_COMMANDS)}"
        )

    cmd = list(agent_config["cmd"])

    # Add model flag if specified
    if model and agent_name == "claude":
        cmd.extend(["--model", model])

    # Append instruction as the prompt
    cmd.append(instruction)

    print(f"  Running {agent_name}{'  (verbose)' if verbose else ''}...")
    start = time.time()

    try:
        if verbose:
            # Stream output in real time, also capture it
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(workdir),
            )
            output_lines = []
            for line in process.stdout:
                print(f"  │ {line}", end="")
                output_lines.append(line)
            process.wait(timeout=1800)
            elapsed = time.time() - start
            full_output = "".join(output_lines)
            return {
                "returncode": process.returncode,
                "stdout": full_output[-10000:],
                "stderr": "",
                "elapsed_seconds": round(elapsed, 1),
            }
        else:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=1800,  # 30 min timeout
                cwd=str(workdir),
            )
            elapsed = time.time() - start
            return {
                "returncode": result.returncode,
                "stdout": result.stdout[-5000:] if result.stdout else "",
                "stderr": result.stderr[-2000:] if result.stderr else "",
                "elapsed_seconds": round(elapsed, 1),
            }
    except (subprocess.TimeoutExpired, Exception):
        elapsed = time.time() - start
        if verbose and "process" in locals():
            process.kill()
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": "TIMEOUT after 30 minutes",
            "elapsed_seconds": round(elapsed, 1),
        }


def run_oracle(task_name: str, workdir: Path) -> dict:
    """Run the oracle solution."""
    task_dir = TASKS_DIR / task_name
    solve_script = task_dir / "solution" / "solve.py"
    db_path = str(workdir / "database.duckdb")  # symlinked in workdir
    output_path = str(workdir / "output.csv")

    result = subprocess.run(
        [sys.executable, str(solve_script), db_path, output_path],
        capture_output=True,
        text=True,
    )
    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def run_tests(task_name: str, workdir: Path) -> dict:
    """Run pytest on the task's test_outputs.py. Returns test results."""
    task_dir = TASKS_DIR / task_name
    test_file = task_dir / "tests" / "test_outputs.py"

    # Determine ground truth path from task name
    gt_name = task_name.replace("mimic-", "")
    # Try compressed first, fall back to uncompressed
    gt_gz = GROUND_TRUTH_DIR / f"{gt_name}.csv.gz"
    gt_csv = GROUND_TRUTH_DIR / f"{gt_name}.csv"
    gt_path = str(gt_gz if gt_gz.exists() else gt_csv)
    output_path = str(workdir / "output.csv")

    env = {
        **os.environ,
        "AGENT_OUTPUT_PATH": output_path,
        "GROUND_TRUTH_PATH": gt_path,
    }

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(test_file),
            "-v",
            "--tb=short",
            "--no-header",
        ],
        capture_output=True,
        text=True,
        env=env,
    )

    # Parse pass/fail counts from pytest output
    # Look for summary line like "7 passed" or "5 passed, 2 failed"
    import re

    passed = failed = errors = 0
    for line in result.stdout.strip().split("\n"):
        # Match pytest summary patterns
        m = re.search(r"(\d+) passed", line)
        if m:
            passed = int(m.group(1))
        m = re.search(r"(\d+) failed", line)
        if m:
            failed = int(m.group(1))
        m = re.search(r"(\d+) error", line)
        if m:
            errors = int(m.group(1))

    total = passed + failed + errors
    reward = passed / total if total > 0 else 0.0

    return {
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "total": total,
        "reward": round(reward, 4),
        "pytest_output": result.stdout,
        "pytest_stderr": result.stderr,
    }


def main():
    parser = argparse.ArgumentParser(description="ClinSkillsBench evaluation harness")
    parser.add_argument("--task", required=True, help="Task name (e.g., mimic-sirs)")
    parser.add_argument(
        "--condition",
        choices=["no-skill", "with-skill", "self-generated"],
        help="Evaluation condition",
    )
    parser.add_argument("--agent", choices=list(AGENT_COMMANDS), help="Agent to use")
    parser.add_argument("--model", help="Model override (e.g., opus, sonnet, haiku)")
    parser.add_argument("--trial", type=int, default=1, help="Trial number")
    parser.add_argument(
        "--oracle", action="store_true", help="Run oracle solution only"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Stream agent output in real time",
    )
    args = parser.parse_args()

    if not args.oracle and (not args.condition or not args.agent):
        parser.error("--condition and --agent are required unless --oracle is set")

    # Verify prerequisites
    task_dir = TASKS_DIR / args.task
    if not task_dir.exists():
        print(f"Error: Task directory not found: {task_dir}")
        sys.exit(1)

    agent_db_path = _resolve_agent_db(args.task)
    if not Path(agent_db_path).exists():
        task_key = args.task.replace("mimic-", "")
        print(f"Error: Agent DB not found: {agent_db_path}")
        print(f"Run: python benchmark/shared/setup_agent_db.py --task {task_key}")
        sys.exit(1)

    # Create working directory
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    if args.oracle:
        run_id = f"oracle_{args.task}_{timestamp}"
    else:
        run_id = f"{args.task}_{args.condition}_{args.agent}_{args.model or 'default'}_t{args.trial}_{timestamp}"

    workdir = RESULTS_DIR / run_id
    workdir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'=' * 60}")
    print(f"ClinSkillsBench: {args.task}")
    if args.oracle:
        print("Mode: Oracle solution")
    else:
        print(
            f"Condition: {args.condition} | Agent: {args.agent} | Model: {args.model or 'default'}"
        )
    print(f"Working dir: {workdir}")
    print(f"{'=' * 60}\n")

    # Set up workdir with symlinked data
    setup_workdir(args.task, workdir)

    # Run oracle or agent
    injected_skills = []
    try:
        if args.oracle:
            print("Running oracle solution...")
            agent_result = run_oracle(args.task, workdir)
            if agent_result["returncode"] != 0:
                print(f"Oracle failed: {agent_result['stderr']}")
        else:
            # Inject skill if with-skill condition
            if args.condition == "with-skill":
                print("Injecting skills...")
                injected_skills = inject_skill(args.task, args.agent)

            # Prepare instruction
            instruction = prepare_instruction(args.task, workdir, args.condition)

            # Save instruction for reference
            (workdir / "instruction.md").write_text(instruction)

            # Run agent
            agent_result = run_agent(
                instruction, args.agent, workdir, args.model, verbose=args.verbose
            )
            print(
                f"  Agent finished in {agent_result['elapsed_seconds']}s "
                f"(exit code: {agent_result['returncode']})"
            )

        # Check if output was produced
        output_file = workdir / "output.csv"
        if not output_file.exists():
            print(f"\nNo output file produced at {output_file}")
            test_results = {
                "passed": 0,
                "failed": 0,
                "errors": 1,
                "total": 1,
                "reward": 0.0,
                "pytest_output": "No output file",
                "pytest_stderr": "",
            }
        else:
            print(f"\nOutput produced: {output_file}")
            print("Running tests...")
            test_results = run_tests(args.task, workdir)

        # Print results
        print(f"\n{'=' * 60}")
        print(f"Results: {test_results['passed']}/{test_results['total']} tests passed")
        print(f"Reward: {test_results['reward']}")
        print(f"{'=' * 60}")
        print(f"\nPytest output:\n{test_results.get('pytest_output', '')}")

        # Save full result
        full_result = {
            "task": args.task,
            "condition": args.condition if not args.oracle else "oracle",
            "agent": args.agent if not args.oracle else "oracle",
            "model": args.model,
            "trial": args.trial,
            "timestamp": timestamp,
            "run_id": run_id,
            "agent_result": agent_result,
            "test_results": test_results,
        }
        result_file = workdir / "result.json"
        with open(result_file, "w") as f:
            json.dump(full_result, f, indent=2, default=str)
        print(f"\nFull result saved to: {result_file}")

    finally:
        # Clean up injected skills
        if injected_skills:
            print("\nCleaning up skills...")
            cleanup_skills(injected_skills)


if __name__ == "__main__":
    main()
