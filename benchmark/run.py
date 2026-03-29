"""M4Bench evaluation harness.

Orchestrates: task setup -> agent invocation -> output collection -> test execution.

Usage:
    # Run a single task
    python benchmark/run.py --task mimic-sirs-24h --condition with-skill --agent claude

    # Run all variants of a task family
    python benchmark/run.py --family sofa --condition no-skill --agent claude

    # Run all tasks
    python benchmark/run.py --task all --condition with-skill --agent claude --model opus

    # List available tasks
    python benchmark/run.py --list

    # Isolated mode (filesystem sandboxed, network tools blocked)
    python benchmark/run.py --task mimic-sirs-24h --condition no-skill --agent claude --isolated
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

# Ensure lib/ is importable
sys.path.insert(0, str(Path(__file__).parent))

from lib.db import list_task_dirs, load_task_config, resolve_task_dir

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


def _resolve_agent_db(task_name: str, schema: str = "native") -> str:
    """Find the agent DB for a task and schema condition."""
    task_key = task_name.replace("mimic-", "")
    if schema == "native":
        task_db = AGENT_DB_DIR / f"mimic_iv_{task_key}.duckdb"
        generic_db = AGENT_DB_DIR / "mimic_iv.duckdb"
    else:
        # obfuscated or restructured
        task_db = AGENT_DB_DIR / f"{schema}_{task_key}.duckdb"
        generic_db = AGENT_DB_DIR / f"{schema}_mimic_iv.duckdb"
    return str(task_db if task_db.exists() else generic_db)


def setup_workdir(task_name: str, workdir: Path, schema: str = "native") -> None:
    """Prepare the agent's working directory with a symlink to a cached DB copy.

    Symlinks to a per-task cache in /tmp (not to agent_db/ directly) so that
    DuckDB WAL writes don't mutate the source, and the results directory
    stays lightweight.
    """
    cached_db = _get_cached_db(task_name, schema)
    agent_db_link = workdir / "database.duckdb"
    if not agent_db_link.exists():
        agent_db_link.symlink_to(cached_db)


def _get_cached_db(task_name: str, schema: str = "native") -> Path:
    """Get or create a cached copy of the agent DB.

    Databases are cached per task key in /tmp so that multiple runs don't
    each copy 2+ GB from agent_db/, and DuckDB WAL writes never touch the
    source.
    """
    task_key = task_name.replace("mimic-", "")
    DB_CACHE.mkdir(parents=True, exist_ok=True)

    if schema == "native":
        cache_name = f"mimic_iv_{task_key}.duckdb"
    else:
        cache_name = f"{schema}_{task_key}.duckdb"

    cached_db = DB_CACHE / cache_name

    lock = _get_db_cache_lock(cache_name)
    with lock:
        if not cached_db.exists():
            agent_db_src = Path(_resolve_agent_db(task_name, schema)).resolve()
            size_gb = agent_db_src.stat().st_size / 1e9
            print(f"  Caching database for {task_key}/{schema} ({size_gb:.1f} GB)...")
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
    skip = {"database.duckdb", "database.duckdb.wal", ".claude", "_home"}
    for item in workdir.iterdir():
        if item.name in skip or item.is_symlink():
            continue
        dest = results_dir / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)


# ── Instruction and skill management ────────────────────────────────────────


def prepare_instruction(
    task_name: str, workdir: Path, condition: str, schema: str = "native"
) -> str:
    """Load instruction.md and fill in paths. Apply schema transforms if needed."""
    task_dir = resolve_task_dir(task_name)
    instruction = (task_dir / "instruction.md").read_text()

    db_path = "./database.duckdb"
    output_path = "./output.csv"

    instruction = instruction.replace("{db_path}", db_path)
    instruction = instruction.replace("{output_path}", output_path)

    if condition == "self-generated":
        instruction += SELF_GEN_PROMPT

    if schema in ("obfuscated", "restructured"):
        from lib.transform import generate_obfuscated_instruction, load_dictionary

        dictionary = load_dictionary()
        instruction = generate_obfuscated_instruction(
            instruction,
            dictionary,
            include_restructured_tables=(schema == "restructured"),
        )

    return instruction


def inject_skill(
    task_name: str, agent_name: str, home: str | None = None
) -> list[Path]:
    """Copy skill files to agent's skill discovery path. Returns created paths."""
    task_dir = resolve_task_dir(task_name)
    skills_dir = task_dir / "skills"

    if not skills_dir.exists():
        return []

    agent_config = AGENT_COMMANDS.get(agent_name, {})
    home = home or str(Path.home())
    created_paths = []

    for skill_path_template in agent_config.get("skill_paths", []):
        target_base = Path(skill_path_template.format(home=home))
        target_base.mkdir(parents=True, exist_ok=True)

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


def inject_all_skills(agent_name: str, home: str | None = None) -> list[Path]:
    """Copy ALL benchmark skills to the agent's skill directory."""
    all_task_dirs = list_task_dirs()
    seen_skills: set[str] = set()
    created_paths: list[Path] = []
    home = home or str(Path.home())
    agent_config = AGENT_COMMANDS.get(agent_name, {})

    for task_dir in all_task_dirs:
        skills_dir = task_dir / "skills"
        if not skills_dir.exists():
            continue
        for skill_dir in skills_dir.iterdir():
            if not skill_dir.is_dir() or skill_dir.name in seen_skills:
                continue
            seen_skills.add(skill_dir.name)
            for tmpl in agent_config.get("skill_paths", []):
                target_base = Path(tmpl.format(home=home))
                target_base.mkdir(parents=True, exist_ok=True)
                target = target_base / skill_dir.name
                if not target.exists():
                    shutil.copytree(skill_dir, target)
                    created_paths.append(target)
                    print(f"  Injected skill: {target}")

    return created_paths


# ── Agent execution ─────────────────────────────────────────────────────────


def run_agent(
    instruction: str,
    agent_name: str,
    workdir: Path,
    model: str | None = None,
    verbose: bool = False,
    isolated: bool = False,
    run_home: Path | None = None,
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

    # Per-run HOME isolation: when set, Claude CLI discovers skills at
    # $HOME/.claude/skills/ and loads $HOME/.claude/CLAUDE.md — both controlled.
    env = None
    if run_home:
        env = {**os.environ, "HOME": str(run_home)}

    print(f"  Running {agent_name}{'  (verbose)' if verbose else ''}...")
    start = time.time()

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(workdir),
            env=env,
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


# ── Task listing ───────────────────────────────────────────────────────────


def list_tasks() -> None:
    """Print available tasks with metadata and exit."""
    task_dirs = list_task_dirs()
    if not task_dirs:
        print("No tasks found.")
        return

    # Group by family (parent directory name)
    families: dict[str, list[tuple[str, str, str]]] = {}
    for td in task_dirs:
        config = load_task_config(td)
        meta = config["metadata"]
        family = td.parent.name
        families.setdefault(family, []).append(
            (meta["name"], meta.get("difficulty", "?"), meta.get("mode", "?"))
        )

    print(f"\nAvailable tasks ({len(task_dirs)} total):\n")
    for family, tasks in sorted(families.items()):
        print(f"  {family}/")
        for name, difficulty, mode in tasks:
            print(f"    {name:<30s}  {difficulty:<8s}  {mode}")
    print(f"\nFamilies: {', '.join(sorted(families))}")


def resolve_tasks(args) -> list[str]:
    """Resolve CLI arguments to a list of task names."""
    if args.list:
        list_tasks()
        sys.exit(0)

    if args.family:
        # Find all tasks under benchmark/tasks/{family}/
        all_dirs = list_task_dirs()
        matched = [
            load_task_config(td)["metadata"]["name"]
            for td in all_dirs
            if td.parent.name == args.family
        ]
        if not matched:
            print(f"Error: No tasks found for family '{args.family}'")
            print("Use --list to see available tasks and families.")
            sys.exit(1)
        return matched

    if args.task == "all":
        return [load_task_config(td)["metadata"]["name"] for td in list_task_dirs()]

    return [args.task]


# ── Single-task execution ──────────────────────────────────────────────────


def run_single_task(
    task_name: str,
    condition: str,
    agent_name: str,
    model: str | None,
    trial: int,
    verbose: bool,
    isolated: bool,
    schema: str = "native",
) -> dict:
    """Run a single benchmark task end-to-end. Returns the full result dict."""
    # Verify prerequisites
    try:
        resolve_task_dir(task_name)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return {"task": task_name, "test_results": {"reward": 0.0}, "error": str(e)}

    agent_db_path = _resolve_agent_db(task_name, schema)
    if not Path(agent_db_path).exists():
        msg = f"Agent DB not found: {agent_db_path}. Run: python benchmark/setup.py --task {task_name}"
        print(f"Error: {msg}")
        return {"task": task_name, "test_results": {"reward": 0.0}, "error": msg}

    # Create working directory
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    schema_tag = f"_{schema}" if schema != "native" else ""
    run_id = f"{task_name}_{condition}{schema_tag}_{agent_name}_{model or 'default'}_t{trial}_{timestamp}"

    if isolated:
        workdir = setup_isolated_workdir(task_name, run_id)
        final_results_dir = RESULTS_DIR / run_id
    else:
        workdir = RESULTS_DIR / run_id
        workdir.mkdir(parents=True, exist_ok=True)
        final_results_dir = None

    print(f"\n{'=' * 60}")
    print(f"M4Bench: {task_name}")
    print(
        f"Condition: {condition} | Schema: {schema} | Agent: {agent_name} | Model: {model or 'default'}"
    )
    if isolated:
        print("Isolation: ON (filesystem sandboxed, network blocked)")
    print(f"Working dir: {workdir}")
    print(f"{'=' * 60}\n")

    # Set up workdir with data
    if not isolated:
        setup_workdir(task_name, workdir, schema)

    # Per-run HOME isolation: when ANTHROPIC_API_KEY is set (Docker / explicit key),
    # create a clean HOME so the agent sees no host CLAUDE.md or personal skills.
    # On bare metal with OAuth (no key set), skip — auth requires the real HOME.
    run_home = None
    use_run_home = os.environ.get("ANTHROPIC_API_KEY")

    if use_run_home:
        run_home = workdir / "_home"
        (run_home / ".claude" / "skills").mkdir(parents=True, exist_ok=True)
        print("  Per-run HOME isolation: ON (clean environment)")

    # Run agent
    injected_skills = []
    try:
        skill_home = str(run_home) if run_home else None
        if condition == "with-skill":
            print("Injecting skills...")
            injected_skills = inject_skill(task_name, agent_name, home=skill_home)
        elif condition == "with-skill-all":
            print("Injecting all benchmark skills...")
            injected_skills = inject_all_skills(agent_name, home=skill_home)

        instruction = prepare_instruction(task_name, workdir, condition, schema)
        (workdir / "instruction.md").write_text(instruction)

        agent_result = run_agent(
            instruction,
            agent_name,
            workdir,
            model,
            verbose=verbose,
            isolated=isolated,
            run_home=run_home,
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

            test_results = evaluate(task_name, str(output_file))

        # Print results
        print(f"\n{'=' * 60}")
        print(f"Results: {test_results['passed']}/{test_results['total']} tests passed")
        print(f"Reward: {test_results['reward']}")
        print(f"{'=' * 60}")
        print(f"\nPytest output:\n{test_results.get('pytest_output', '')}")

        # Save full result
        full_result = {
            "task": task_name,
            "condition": condition,
            "schema": schema,
            "agent": agent_name,
            "model": model,
            "trial": trial,
            "isolated": isolated,
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

        return full_result

    finally:
        # When using per-run HOME, skills live in workdir — no host cleanup needed.
        # On bare metal (no run_home), clean up injected skills from ~/.claude/skills/.
        if injected_skills and not run_home:
            print("Cleaning up skills...")
            for p in injected_skills:
                if p.exists():
                    shutil.rmtree(p)
        if final_results_dir:
            print(f"\nCopying results to {final_results_dir}...")
            copy_results_back(workdir, final_results_dir)
            print(f"Results available at: {final_results_dir}")


# ── Thread safety ──────────────────────────────────────────────────────────

_db_cache_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
_db_cache_locks_guard = threading.Lock()


def _get_db_cache_lock(cache_name: str) -> threading.Lock:
    """Get a per-cache-name lock for thread-safe DB caching."""
    with _db_cache_locks_guard:
        return _db_cache_locks[cache_name]


# Skill injection locks: keyed by skill directory name. Serializes parallel
# with-skill runs that inject the same skill (e.g., sirs-24h and sirs-24h-raw
# both use "sirs-criteria" but with different content).
_skill_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
_skill_locks_guard = threading.Lock()


def _get_skill_locks(task_name: str) -> list[threading.Lock]:
    """Return locks for all skill directories this task would inject."""
    try:
        task_dir = resolve_task_dir(task_name)
    except FileNotFoundError:
        return []
    skills_dir = task_dir / "skills"
    if not skills_dir.exists():
        return []
    locks = []
    with _skill_locks_guard:
        for skill_dir in sorted(skills_dir.iterdir()):
            if skill_dir.is_dir():
                locks.append(_skill_locks[skill_dir.name])
    return locks


# ── Parallel execution ─────────────────────────────────────────────────────

_progress_lock = threading.Lock()


def _print_progress(done: int, total: int, running: set[str]) -> None:
    """Print current progress (thread-safe)."""
    with _progress_lock:
        running_str = ", ".join(sorted(running)) if running else "none"
        queued = total - done - len(running)
        print(
            f"\n[{done}/{total} done] Running: {running_str} | Queued: {queued}",
            flush=True,
        )


def _run_parallel(
    run_matrix: list[tuple[str, int]],
    condition: str,
    agent_name: str,
    model: str | None,
    verbose: bool,
    isolated: bool,
    schema: str,
    max_workers: int,
) -> list[dict]:
    """Execute runs in parallel using ThreadPoolExecutor."""
    total = len(run_matrix)
    done = 0
    running: set[str] = set()
    results: list[dict] = []

    def _run_one(task_name: str, trial: int) -> dict:
        nonlocal done
        key = f"{task_name}/t{trial}"
        with _progress_lock:
            running.add(key)
        _print_progress(done, total, running)

        # Acquire skill locks for with-skill conditions to prevent
        # concurrent inject/cleanup of same skill directory
        skill_locks = []
        if condition in ("with-skill", "with-skill-all"):
            skill_locks = _get_skill_locks(task_name)
            skill_locks.sort(key=id)  # consistent order prevents deadlock
            for lock in skill_locks:
                lock.acquire()

        try:
            result = run_single_task(
                task_name,
                condition,
                agent_name,
                model,
                trial,
                verbose,
                isolated,
                schema,
            )
        except Exception as e:
            result = {
                "task": task_name,
                "trial": trial,
                "condition": condition,
                "test_results": {"reward": 0.0},
                "error": str(e),
            }
        finally:
            for lock in skill_locks:
                lock.release()

        # Print single-line completion
        reward = result.get("test_results", {}).get("reward", 0.0)
        elapsed = result.get("agent_result", {}).get("elapsed_seconds", 0)
        with _progress_lock:
            running.discard(key)
            done += 1
        _print_progress(done, total, running)
        with _progress_lock:
            print(f"  Completed: {key} -> reward={reward:.4f} ({elapsed:.0f}s)")

        return result

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_key = {}
        for task_name, trial in run_matrix:
            future = executor.submit(_run_one, task_name, trial)
            future_to_key[future] = (task_name, trial)

        for future in as_completed(future_to_key):
            task_name, trial = future_to_key[future]
            try:
                result = future.result()
            except Exception as e:
                result = {
                    "task": task_name,
                    "trial": trial,
                    "condition": condition,
                    "test_results": {"reward": 0.0},
                    "error": str(e),
                }
            results.append(result)

    return results


# ── Summary ────────────────────────────────────────────────────────────────


def _print_summary(results: list[dict], seeds: int) -> None:
    """Print batch summary with per-task mean ± std when seeds > 1."""
    print(f"\n{'=' * 78}")
    print("BATCH SUMMARY")
    print(f"{'=' * 78}")

    if seeds > 1:
        # Group by task
        by_task: dict[str, list[float]] = defaultdict(list)
        for r in results:
            task = r.get("task", "?")
            reward = r.get("test_results", {}).get("reward", 0.0)
            by_task[task].append(reward)

        cond = results[0].get("condition", "?")
        print(
            f"{'Task':<30s}  {'Condition':<16s}  {'Mean':>7s}  {'Std':>7s}  {'N':>3s}"
        )
        print(f"{'-' * 30}  {'-' * 16}  {'-' * 7}  {'-' * 7}  {'-' * 3}")

        all_means = []
        for task, rewards in sorted(by_task.items()):
            mean_r = statistics.mean(rewards)
            std_r = statistics.stdev(rewards) if len(rewards) > 1 else 0.0
            all_means.append(mean_r)
            print(
                f"{task:<30s}  {cond:<16s}  {mean_r:>7.4f}  {std_r:>7.4f}  {len(rewards):>3d}"
            )

        overall_mean = statistics.mean(all_means)
        overall_std = statistics.stdev(all_means) if len(all_means) > 1 else 0.0
        print(f"{'-' * 30}  {'-' * 16}  {'-' * 7}  {'-' * 7}  {'-' * 3}")
        print(
            f"{'Aggregate':<30s}  {'':<16s}  {overall_mean:>7.4f}  {overall_std:>7.4f}"
        )
    else:
        print(f"{'Task':<30s}  {'Condition':<16s}  {'Reward':>7s}  {'Time':>7s}")
        print(f"{'-' * 30}  {'-' * 16}  {'-' * 7}  {'-' * 7}")
        for r in results:
            task = r.get("task", "?")
            cond = r.get("condition", "?")
            reward = r.get("test_results", {}).get("reward", 0.0)
            elapsed = r.get("agent_result", {}).get("elapsed_seconds", 0)
            print(f"{task:<30s}  {cond:<16s}  {reward:>7.4f}  {elapsed:>6.1f}s")
        mean_reward = sum(
            r.get("test_results", {}).get("reward", 0.0) for r in results
        ) / len(results)
        print(f"{'-' * 30}  {'-' * 16}  {'-' * 7}  {'-' * 7}")
        print(f"{'Mean':<30s}  {'':<16s}  {mean_reward:>7.4f}")

    print(f"{'=' * 78}")


# ── Main ────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="M4Bench evaluation harness")
    task_group = parser.add_mutually_exclusive_group(required=True)
    task_group.add_argument(
        "--task",
        help="Task name (e.g., mimic-sirs-24h) or 'all' for every task",
    )
    task_group.add_argument(
        "--family",
        help="Run all variants of a task family (e.g., sirs, sofa)",
    )
    task_group.add_argument(
        "--list",
        action="store_true",
        help="List available tasks and exit",
    )
    parser.add_argument(
        "--condition",
        choices=["no-skill", "with-skill", "with-skill-all", "self-generated"],
        help="Evaluation condition",
    )
    parser.add_argument("--agent", choices=list(AGENT_COMMANDS), help="Agent to use")
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
    parser.add_argument(
        "--schema",
        choices=["native", "obfuscated", "restructured"],
        default="native",
        help="Database schema condition for contamination analysis (default: native)",
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=1,
        help="Max concurrent task runs (default: 1, recommended max: 4 on 18GB RAM)",
    )
    parser.add_argument(
        "--seeds",
        type=int,
        default=1,
        help="Number of seeds per task (each gets trial=1..N)",
    )
    args = parser.parse_args()

    task_names = resolve_tasks(args)

    # --condition and --agent are required when actually running tasks
    if not args.condition:
        parser.error("--condition is required when running tasks")
    if not args.agent:
        parser.error("--agent is required when running tasks")

    if args.parallel > 4:
        print(
            f"Warning: --parallel {args.parallel} exceeds recommended max of 4 on 18GB RAM"
        )

    # Build run matrix: (task_name, trial) for all tasks x seeds
    run_matrix = [
        (task_name, trial)
        for task_name in task_names
        for trial in range(1, args.seeds + 1)
    ]

    print(
        f"\nRun matrix: {len(run_matrix)} runs ({len(task_names)} tasks x {args.seeds} seeds)"
    )
    if args.parallel > 1:
        print(f"Parallelism: {args.parallel} concurrent runs")
    print()

    # Execute runs
    if args.parallel <= 1:
        # Sequential execution (original behavior)
        results = []
        for task_name, trial in run_matrix:
            result = run_single_task(
                task_name,
                args.condition,
                args.agent,
                args.model,
                trial,
                args.verbose,
                args.isolated,
                args.schema,
            )
            results.append(result)
    else:
        # Parallel execution
        results = _run_parallel(
            run_matrix,
            args.condition,
            args.agent,
            args.model,
            args.verbose,
            args.isolated,
            args.schema,
            args.parallel,
        )

    # Print summary
    if len(results) > 1:
        _print_summary(results, args.seeds)

    # Save batch result JSON
    if len(results) > 1:
        batch_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        batch_path = RESULTS_DIR / f"batch_{batch_ts}.json"
        batch_data = {
            "condition": args.condition,
            "agent": args.agent,
            "model": args.model,
            "schema": args.schema,
            "parallel": args.parallel,
            "seeds": args.seeds,
            "results": results,
        }
        with open(batch_path, "w") as f:
            json.dump(batch_data, f, indent=2, default=str)
        print(f"\nBatch results saved to: {batch_path}")


if __name__ == "__main__":
    main()
