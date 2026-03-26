"""Run pytest evaluation and parse results."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

TEST_FILE = Path(__file__).parent / "test_task.py"


def run_tests(
    task_dir: str | Path,
    output_path: str | Path,
    ground_truth_path: str | Path,
) -> dict:
    """Run pytest on test_task.py and return parsed results.

    Args:
        task_dir: Path to the task directory (contains task.toml).
        output_path: Path to agent's output CSV.
        ground_truth_path: Path to ground truth CSV.

    Returns:
        Dict with passed, failed, errors, total, reward, pytest_output, pytest_stderr.
    """
    env = {
        **os.environ,
        "TASK_DIR": str(task_dir),
        "AGENT_OUTPUT_PATH": str(output_path),
        "GROUND_TRUTH_PATH": str(ground_truth_path),
    }

    # Prefer the venv Python so pytest/pandas are available even when
    # the harness is invoked via a bare `python` outside the venv.
    venv_python = Path(__file__).resolve().parents[2] / ".venv" / "bin" / "python"
    python = str(venv_python) if venv_python.exists() else sys.executable

    result = subprocess.run(
        [
            python,
            "-m",
            "pytest",
            str(TEST_FILE),
            "-v",
            "--tb=short",
            "--no-header",
        ],
        capture_output=True,
        text=True,
        env=env,
    )

    # Detect pytest infrastructure failures (e.g. missing pytest module)
    if result.returncode != 0 and not result.stdout.strip():
        detail = result.stderr.strip() or f"pytest exited with code {result.returncode}"
        raise RuntimeError(f"Pytest failed to run: {detail}")

    passed = failed = errors = 0
    for line in result.stdout.strip().split("\n"):
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
