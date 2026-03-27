"""ClinSkillsBench evaluation harness.

Orchestrates: task setup -> agent invocation -> output collection -> test execution.

Usage:
    # Run with skill
    python benchmark/run.py --task mimic-sirs-24h --condition with-skill --agent claude

    # Run without skill
    python benchmark/run.py --task mimic-sirs-24h --condition no-skill --agent claude

    # Specify model (for claude)
    python benchmark/run.py --task mimic-sirs-24h --condition with-skill --agent claude --model opus

    # Isolated mode (filesystem sandboxed, network tools blocked, full trace captured)
    python benchmark/run.py --task mimic-sirs-24h --condition no-skill --agent claude --isolated
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure lib/ is importable
sys.path.insert(0, str(Path(__file__).parent))

from lib.db import resolve_task_dir

BENCHMARK_ROOT = Path(__file__).parent
AGENT_DB_DIR = BENCHMARK_ROOT / "agent_db"
RESULTS_DIR = BENCHMARK_ROOT / "results"
ISOLATED_BASE = Path(tempfile.gettempdir()) / "clinskillsbench"
DB_CACHE = ISOLATED_BASE / "_db_cache"
SANDBOX_HOOK = BENCHMARK_ROOT / "lib" / "sandbox_hook.py"

# Tools to deny in isolated mode — blocks internet access from the agent.
NETWORK_DENY_TOOLS = ",".join(
    [
        "WebFetch",
        "WebSearch",
        "Bash(curl *)",
        "Bash(wget *)",
        "Bash(python -c *)",
        "Bash(python3 -c *)",
        "Bash(node -e *)",
        "Bash(npx *)",
    ]
)

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


# ── Isolated workdir setup ──────────────────────────────────────────────────


def _create_isolated_settings(workdir: Path) -> Path:
    """Write a .claude/settings.json in the workdir that enforces the sandbox hook."""
    claude_dir = workdir / ".claude"
    claude_dir.mkdir(exist_ok=True)
    settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Read|Write|Edit|Glob|Grep|Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"python3 {SANDBOX_HOOK} {workdir}",
                        }
                    ],
                }
            ]
        }
    }
    settings_path = claude_dir / "settings.json"
    settings_path.write_text(json.dumps(settings, indent=2))
    return settings_path


# ── Database and workdir setup ──────────────────────────────────────────────


def _resolve_agent_db(task_name: str) -> str:
    """Find the agent DB for a task."""
    task_key = task_name.replace("mimic-", "")
    task_db = AGENT_DB_DIR / f"mimic_iv_{task_key}.duckdb"
    generic_db = AGENT_DB_DIR / "mimic_iv.duckdb"
    return str(task_db if task_db.exists() else generic_db)


def setup_workdir(task_name: str, workdir: Path) -> None:
    """Prepare the agent's working directory with a symlink to a cached DB copy.

    Symlinks to a per-task cache in /tmp (not to agent_db/ directly) so that
    DuckDB WAL writes don't mutate the source, and the results directory
    stays lightweight.
    """
    cached_db = _get_cached_db(task_name)
    agent_db_link = workdir / "database.duckdb"
    if not agent_db_link.exists():
        agent_db_link.symlink_to(cached_db)


def _get_cached_db(task_name: str) -> Path:
    """Get or create a cached copy of the agent DB.

    Databases are cached per task key in /tmp so that multiple runs don't
    each copy 2+ GB from agent_db/, and DuckDB WAL writes never touch the
    source.
    """
    task_key = task_name.replace("mimic-", "")
    DB_CACHE.mkdir(parents=True, exist_ok=True)
    cached_db = DB_CACHE / f"mimic_iv_{task_key}.duckdb"

    if not cached_db.exists():
        agent_db_src = Path(_resolve_agent_db(task_name)).resolve()
        size_gb = agent_db_src.stat().st_size / 1e9
        print(f"  Caching database for {task_key} ({size_gb:.1f} GB)...")
        shutil.copy2(agent_db_src, cached_db)
        wal_src = agent_db_src.with_suffix(".duckdb.wal")
        if wal_src.exists():
            shutil.copy2(wal_src, cached_db.with_suffix(".duckdb.wal"))

    return cached_db


def setup_isolated_workdir(task_name: str, run_id: str) -> Path:
    """Create an isolated workdir in /tmp with a copy of the database.

    The database is copied (not symlinked) from the per-task cache so that
    the sandbox hook doesn't block access to it — the file lives inside the
    allowed directory.
    """
    workdir = ISOLATED_BASE / run_id
    workdir.mkdir(parents=True, exist_ok=True)

    # Copy DB from cache into workdir (same filesystem = fast)
    cached_db = _get_cached_db(task_name)
    db_dest = workdir / "database.duckdb"
    if not db_dest.exists():
        print("  Copying database into workdir from cache...")
        shutil.copy2(cached_db, db_dest)
        wal_src = cached_db.with_suffix(".duckdb.wal")
        if wal_src.exists():
            shutil.copy2(wal_src, db_dest.with_suffix(".duckdb.wal"))

    # Install sandbox hook
    _create_isolated_settings(workdir)
    print(f"  Sandbox hook: {SANDBOX_HOOK} (allowed dir: {workdir})")

    return workdir


def copy_results_back(workdir: Path, results_dir: Path) -> None:
    """Copy result files from the isolated workdir to benchmark/results/.

    Skips the database and sandbox config (only copies useful outputs).
    """
    results_dir.mkdir(parents=True, exist_ok=True)
    skip = {"database.duckdb", "database.duckdb.wal", ".claude"}
    for item in workdir.iterdir():
        if item.name in skip or item.is_symlink():
            continue
        dest = results_dir / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)


# ── Instruction and skill management ────────────────────────────────────────


def prepare_instruction(task_name: str, workdir: Path, condition: str) -> str:
    """Load instruction.md and fill in paths."""
    task_dir = resolve_task_dir(task_name)
    instruction = (task_dir / "instruction.md").read_text()

    db_path = "./database.duckdb"
    output_path = "./output.csv"

    instruction = instruction.replace("{db_path}", db_path)
    instruction = instruction.replace("{output_path}", output_path)

    if condition == "self-generated":
        instruction += SELF_GEN_PROMPT

    return instruction


def inject_skill(task_name: str, agent_name: str) -> list[Path]:
    """Copy skill files to agent's skill discovery path. Returns paths for cleanup."""
    task_dir = resolve_task_dir(task_name)
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


# ── Agent execution ─────────────────────────────────────────────────────────


def run_agent(
    instruction: str,
    agent_name: str,
    workdir: Path,
    model: str | None = None,
    verbose: bool = False,
    isolated: bool = False,
) -> dict:
    """Invoke an agent CLI with the instruction. Returns result dict."""
    agent_config = AGENT_COMMANDS.get(agent_name)
    if not agent_config:
        raise ValueError(
            f"Unknown agent: {agent_name}. Available: {list(AGENT_COMMANDS)}"
        )

    cmd = list(agent_config["cmd"])

    if model and agent_name == "claude":
        cmd.extend(["--model", model])

    if isolated and agent_name == "claude":
        cmd.extend(["--disallowedTools", NETWORK_DENY_TOOLS])

    # Capture structured trace for claude
    trace_path = workdir / "trace.jsonl"
    use_stream_json = agent_name == "claude"
    if use_stream_json:
        cmd.extend(["--output-format", "stream-json", "--verbose"])

    cmd.append(instruction)

    print(f"  Running {agent_name}{'  (verbose)' if verbose else ''}...")
    start = time.time()

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(workdir),
        )
        output_lines = []
        with open(trace_path, "w") as trace_file:
            for line in process.stdout:
                if use_stream_json:
                    trace_file.write(line)
                    if verbose:
                        _print_trace_line(line)
                else:
                    trace_file.write(line)
                    if verbose:
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
            "trace_file": str(trace_path),
        }
    except (subprocess.TimeoutExpired, Exception):
        elapsed = time.time() - start
        if "process" in locals():
            process.kill()
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": "TIMEOUT after 30 minutes",
            "elapsed_seconds": round(elapsed, 1),
            "trace_file": str(trace_path),
        }


def _print_trace_line(line: str) -> None:
    """Print a human-readable summary of a stream-json trace line.

    The stream-json format emits newline-delimited JSON with varying schemas.
    We extract what we can and fall back to printing the raw line.
    """
    line = line.rstrip()
    if not line:
        return

    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        print(f"  │ {line}")
        return

    etype = event.get("type", "")

    # Stream events: content deltas (text, tool use)
    if etype == "stream_event":
        inner = event.get("event", {})
        delta = inner.get("delta", {})
        delta_type = delta.get("type", "")

        if delta_type == "text_delta":
            text = delta.get("text", "")
            if text.strip():
                for text_line in text.splitlines():
                    if text_line.strip():
                        print(f"  │ {text_line}")

        elif delta_type == "input_json_delta":
            pass  # Partial tool input, noisy — skip

    # System events (retries, errors)
    elif etype == "system":
        subtype = event.get("subtype", "")
        if subtype == "api_retry":
            print(f"  │ [retry] attempt {event.get('attempt', '?')}")

    # Result event (final output)
    elif etype == "result":
        result = event.get("result", "")
        if result:
            for text_line in str(result).splitlines()[:10]:
                print(f"  │ {text_line}")

    # Catch-all for assistant messages (may appear in some formats)
    elif etype == "assistant":
        msg = event.get("message", {})
        for block in msg.get("content", []):
            if block.get("type") == "text":
                for text_line in block["text"].splitlines():
                    if text_line.strip():
                        print(f"  │ {text_line}")
            elif block.get("type") == "tool_use":
                tool = block.get("name", "?")
                inp = block.get("input", {})
                if tool == "Bash":
                    print(f"  │ [{tool}] {inp.get('command', '')[:120]}")
                elif tool in ("Read", "Write", "Edit"):
                    print(f"  │ [{tool}] {inp.get('file_path', '')}")
                elif tool in ("Glob", "Grep"):
                    print(f"  │ [{tool}] {inp.get('pattern', '')}")
                else:
                    print(f"  │ [{tool}]")


# ── Main ────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="ClinSkillsBench evaluation harness")
    parser.add_argument(
        "--task", required=True, help="Task name (e.g., mimic-sirs-24h)"
    )
    parser.add_argument(
        "--condition",
        required=True,
        choices=["no-skill", "with-skill", "self-generated"],
        help="Evaluation condition",
    )
    parser.add_argument(
        "--agent", required=True, choices=list(AGENT_COMMANDS), help="Agent to use"
    )
    parser.add_argument("--model", help="Model override (e.g., opus, sonnet, haiku)")
    parser.add_argument("--trial", type=int, default=1, help="Trial number")
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Stream agent output in real time",
    )
    parser.add_argument(
        "--isolated",
        action="store_true",
        help="Run in isolated mode: filesystem sandboxed, network tools blocked, full trace captured",
    )
    args = parser.parse_args()

    # Verify prerequisites
    try:
        resolve_task_dir(args.task)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    agent_db_path = _resolve_agent_db(args.task)
    if not Path(agent_db_path).exists():
        print(f"Error: Agent DB not found: {agent_db_path}")
        print(f"Run: python benchmark/setup.py --task {args.task}")
        sys.exit(1)

    # Create working directory
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_id = f"{args.task}_{args.condition}_{args.agent}_{args.model or 'default'}_t{args.trial}_{timestamp}"

    if args.isolated:
        workdir = setup_isolated_workdir(args.task, run_id)
        final_results_dir = RESULTS_DIR / run_id
    else:
        workdir = RESULTS_DIR / run_id
        workdir.mkdir(parents=True, exist_ok=True)
        final_results_dir = None

    print(f"\n{'=' * 60}")
    print(f"ClinSkillsBench: {args.task}")
    print(
        f"Condition: {args.condition} | Agent: {args.agent} | Model: {args.model or 'default'}"
    )
    if args.isolated:
        print("Isolation: ON (filesystem sandboxed, network blocked)")
    print(f"Working dir: {workdir}")
    print(f"{'=' * 60}\n")

    # Set up workdir with data
    if not args.isolated:
        setup_workdir(args.task, workdir)

    # Run agent
    injected_skills = []
    try:
        if args.condition == "with-skill":
            print("Injecting skills...")
            injected_skills = inject_skill(args.task, args.agent)

        instruction = prepare_instruction(args.task, workdir, args.condition)
        (workdir / "instruction.md").write_text(instruction)

        agent_result = run_agent(
            instruction,
            args.agent,
            workdir,
            args.model,
            verbose=args.verbose,
            isolated=args.isolated,
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
            from evaluate import evaluate

            test_results = evaluate(args.task, str(output_file))

        # Print results
        print(f"\n{'=' * 60}")
        print(f"Results: {test_results['passed']}/{test_results['total']} tests passed")
        print(f"Reward: {test_results['reward']}")
        print(f"{'=' * 60}")
        print(f"\nPytest output:\n{test_results.get('pytest_output', '')}")

        # Save full result
        full_result = {
            "task": args.task,
            "condition": args.condition,
            "agent": args.agent,
            "model": args.model,
            "trial": args.trial,
            "isolated": args.isolated,
            "timestamp": timestamp,
            "run_id": run_id,
            "agent_result": agent_result,
            "test_results": test_results,
        }
        result_file = workdir / "result.json"
        with open(result_file, "w") as f:
            json.dump(full_result, f, indent=2, default=str)
        print(f"\nFull result saved to: {result_file}")

        # Report trace location
        trace_file = workdir / "trace.jsonl"
        if trace_file.exists():
            trace_size = trace_file.stat().st_size / 1024
            print(f"Agent trace: {trace_file} ({trace_size:.0f} KB)")

    finally:
        if injected_skills:
            print("\nCleaning up skills...")
            cleanup_skills(injected_skills)
        if final_results_dir:
            print(f"\nCopying results to {final_results_dir}...")
            copy_results_back(workdir, final_results_dir)
            print(f"Results available at: {final_results_dir}")


if __name__ == "__main__":
    main()
