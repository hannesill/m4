"""Smart experiment matrix for M4Bench.

Runs principled ablations across models, conditions, and schemas without
doing a naive cartesian product.  Each tier answers a specific scientific
question; the default powered profile concentrates statistical power on the
GPT-backed Codex models.

Usage:
    # Preview what would run (dry-run)
    python benchmark/matrix.py --dry-run

    # Run tier 1 only (primary skill ablation)
    python benchmark/matrix.py --tier 1 --agent codex

    # Run a sparse external-provider comparison
    python benchmark/matrix.py --profile provider-comparison --agent claude --dry-run

    # Run tiers 1-3
    python benchmark/matrix.py --tier 1 2 3

    # Run everything
    python benchmark/matrix.py --tier all

    # With parallelism
    python benchmark/matrix.py --tier 1 --parallel 3

    # Skip exact task/model/condition/schema/trial runs that already completed
    python benchmark/matrix.py --tier 1 --skip-existing
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib.db import list_task_dirs, load_task_config
from run import (
    BENCHMARK_REASONING_EFFORT,
    PROVIDER_DEFAULT_REASONING,
    REASONING_EFFORT_CHOICES,
    _resolve_reasoning_effort,
)

BENCHMARK_ROOT = Path(__file__).parent
RESULTS_DIR = BENCHMARK_ROOT / "results"
SEEDS = 5  # default; overridable via --seeds


def resolve_results_root(results_root: str | None = None) -> Path:
    """Resolve the results root used for scheduling and execution."""
    if results_root:
        return Path(results_root).expanduser().resolve()
    return RESULTS_DIR.resolve()


# ── Task classification ──────────────────────────────────────────────────────

ALL_TASKS: list[str] = []
STANDARD_TASKS: list[str] = []
RAW_TASKS: list[str] = []
EXPERT_TASKS: list[str] = []
COMPOSITIONAL_TASKS: list[str] = []  # tasks that combine multiple clinical concepts
CROSS_DB_TASKS: list[str] = []  # eICU tasks (cross-database generalization)
CONTAMINATION_TASKS: list[str] = []  # raw tasks with obfuscated/restructured DBs

AGENT_DB_DIR = BENCHMARK_ROOT / "agent_db"


def _classify_tasks() -> None:
    """Populate task lists from task.toml metadata."""
    for task_dir in sorted(list_task_dirs()):
        config = load_task_config(task_dir)
        name = config["metadata"]["name"]
        mode = config["metadata"].get("mode", "standard")
        difficulty = config["metadata"].get("difficulty", "medium")
        tags = config["metadata"].get("tags", [])

        ALL_TASKS.append(name)

        if mode == "raw":
            RAW_TASKS.append(name)
        else:
            STANDARD_TASKS.append(name)

        if difficulty == "expert":
            EXPERT_TASKS.append(name)

        if "compositional" in tags:
            COMPOSITIONAL_TASKS.append(name)

        if name.startswith("eicu-"):
            CROSS_DB_TASKS.append(name)

        # Check for obfuscated/restructured agent DBs
        task_key = name.replace("mimic-", "").replace("eicu-", "")
        if (AGENT_DB_DIR / f"obfuscated_{task_key}.duckdb").exists():
            CONTAMINATION_TASKS.append(name)


# ── Experiment tiers ─────────────────────────────────────────────────────────


@dataclass
class Tier:
    number: int
    name: str
    question: str
    runs: list[dict] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.runs)


@dataclass(frozen=True)
class AgentModelPlan:
    primary_models: tuple[str, ...]
    hurts_models: tuple[str, ...]
    contamination_models: tuple[str, ...]
    noise_models: tuple[str, ...]


def _model_plan_for_agent(agent: str) -> AgentModelPlan:
    """Return the default model set for each supported agent CLI."""
    if agent == "claude":
        return AgentModelPlan(
            primary_models=("opus", "sonnet"),
            hurts_models=("opus", "sonnet"),
            contamination_models=("sonnet",),
            noise_models=("opus",),
        )
    if agent == "codex":
        return AgentModelPlan(
            primary_models=("gpt-5.5", "gpt-5.4-mini"),
            hurts_models=("gpt-5.5", "gpt-5.4-mini"),
            contamination_models=("gpt-5.4-mini",),
            noise_models=("gpt-5.5",),
        )
    if agent == "gemini":
        return AgentModelPlan(
            primary_models=("gemini-3.1-pro-preview", "gemini-3-flash-preview"),
            hurts_models=("gemini-3.1-pro-preview", "gemini-3-flash-preview"),
            contamination_models=("gemini-3-flash-preview",),
            noise_models=("gemini-3.1-pro-preview",),
        )
    if agent == "pi-ollama":
        return AgentModelPlan(
            primary_models=("qwen3:4b",),
            hurts_models=("qwen3:4b",),
            contamination_models=("qwen3:4b",),
            noise_models=("qwen3:4b",),
        )
    raise ValueError(f"Unsupported agent: {agent}")


def _container_results_root(results_root: Path) -> str:
    """Translate a host results root under benchmark/ into the container path."""
    benchmark_root = BENCHMARK_ROOT.resolve()
    try:
        relative = results_root.resolve().relative_to(benchmark_root)
    except ValueError as e:
        raise ValueError(
            "--results-root must live inside benchmark/ for Docker-backed campaigns"
        ) from e
    return str(Path("/benchmark") / relative)


def _docker_container_name(agent: str, task: str, trial: int) -> str:
    """Generate a unique, Docker-safe container name for a single run."""
    raw = f"m4bench-{agent}-{task}-t{trial}-{os.getpid()}"
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", raw).strip("-").lower()


def _find_latest_result(
    results_root: Path,
    task: str,
    condition: str,
    agent: str,
    model: str,
    schema: str,
    trial: int,
    started_after: float | None = None,
) -> dict | None:
    """Find the newest matching result.json under the campaign root."""
    latest_path = None
    latest_mtime = -1.0

    for result_file in results_root.rglob("result.json"):
        try:
            data = json.loads(result_file.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if (
            data.get("task") == task
            and data.get("condition") == condition
            and data.get("agent") == agent
            and data.get("model") == model
            and data.get("schema", "native") == schema
            and data.get("trial") == trial
        ):
            mtime = result_file.stat().st_mtime
            if started_after is not None and mtime < started_after:
                continue
            if mtime > latest_mtime:
                latest_mtime = mtime
                latest_path = result_file

    if latest_path is None:
        return None
    return json.loads(latest_path.read_text())


def _run_via_bench(
    run: dict,
    condition: str,
    model: str,
    schema: str,
    agent: str,
    results_root: Path,
    max_retries: int = 0,
    retry_delay_seconds: int = 15,
    wait_on_claude_rate_limit: bool = False,
    reasoning_effort: str = BENCHMARK_REASONING_EFFORT,
) -> dict:
    """Execute one publishable run by invoking bench.sh on the host."""
    bench_script = BENCHMARK_ROOT / "bench.sh"
    container_results_root = _container_results_root(results_root)
    container_name = _docker_container_name(agent, run["task"], run["trial"])

    cmd = [
        "bash",
        str(bench_script),
        "--task",
        run["task"],
        "--condition",
        condition,
        "--agent",
        agent,
        "--model",
        model,
        "--trial",
        str(run["trial"]),
        "--schema",
        schema,
        "--results-root",
        container_results_root,
        "--reasoning-effort",
        reasoning_effort,
        "--max-retries",
        str(max_retries),
        "--retry-delay-seconds",
        str(retry_delay_seconds),
    ]
    if wait_on_claude_rate_limit:
        cmd.append("--wait-on-claude-rate-limit")

    env = {
        **os.environ,
        "M4BENCH_CONTAINER_NAME": container_name,
    }

    started_after = time.time()
    proc = subprocess.run(cmd, cwd=str(BENCHMARK_ROOT.parent), env=env)

    result = _find_latest_result(
        results_root,
        run["task"],
        condition,
        agent,
        model,
        schema,
        run["trial"],
        started_after=started_after,
    )
    if result is not None:
        return result

    return {
        "task": run["task"],
        "trial": run["trial"],
        "condition": condition,
        "schema": schema,
        "agent": agent,
        "model": model,
        "reasoning_effort": reasoning_effort,
        "resolved_reasoning_effort": _resolve_reasoning_effort(agent, reasoning_effort),
        "test_results": {"reward": 0.0},
        "error": f"bench.sh exited with code {proc.returncode} and produced no result.json",
    }


def build_tiers(
    seeds: int = SEEDS, agent: str = "codex", profile: str = "powered"
) -> list[Tier]:
    """Build the requested experiment matrix profile."""
    if profile == "powered":
        return _build_powered_tiers(seeds=seeds, agent=agent)
    if profile == "provider-comparison":
        return _build_provider_comparison_tiers(seeds=seeds, agent=agent)
    raise ValueError(f"Unsupported profile: {profile}")


def _build_powered_tiers(seeds: int = SEEDS, agent: str = "codex") -> list[Tier]:
    """Build the experiment matrix informed by pilot data.

    Pilot results (1 seed, 27 valid tasks) revealed three task categories:
      - HELPS (11 tasks): skill delta > +0.05, avg +0.32
      - HURTS  (4 tasks): skill delta < -0.05, avg -0.20
      - FLAT  (12 tasks): |delta| <= 0.05

    The matrix concentrates seeds on high-signal tasks and uses fewer seeds
    on ceiling/flat tasks. Model defaults are agent-specific.
    """
    tiers = []
    model_plan = _model_plan_for_agent(agent)

    # ── Task categories from Opus pilot ────────────────────────────────
    # Tasks where skills showed large positive delta (> +0.08).
    HIGH_DELTA = [
        "mimic-urine-output-rate",  # +0.70
        "mimic-urine-output-rate-raw",  # +0.53
        "mimic-ventilation",  # +0.33
        "mimic-vasopressor-equivalents-raw",  # +0.32
        "mimic-creatinine-baseline",  # +0.30
        "mimic-creatinine-baseline-raw",  # +0.30
        "mimic-suspicion-infection",  # +0.29
        "mimic-vasopressor-equivalents",  # +0.28
        "mimic-suspicion-infection-raw",  # +0.21
        "mimic-meld-24h-raw",  # +0.17
        "mimic-kdigo-48h-raw",  # +0.09
    ]

    # Tasks where skills hurt performance (consistent across OASIS family,
    # plus sepsis3 which produced no output with skill).
    SKILL_HURTS = [
        "mimic-sepsis3-raw",  # -0.44 (no output with skill!)
        "mimic-oasis-24h",  # -0.16 (electivesurgery inversion)
        "mimic-oasis-24h-raw",  # -0.10
        "eicu-oasis",  # -0.10
    ]

    # Tasks where skill had negligible effect (|delta| <= 0.05).
    FLAT = [
        t
        for t in ALL_TASKS
        if t not in HIGH_DELTA and t not in SKILL_HURTS and t != "mimic-kdigo-48h"
    ]  # auth failure, separate tier

    all_models = model_plan.primary_models

    # ── Tier 1: High-delta tasks — high-signal primary model set ───────
    # The paper's main finding: skills dramatically help on tasks requiring
    # MIMIC-specific implementation knowledge (itemids, string matching,
    # rolling-window algorithms, formula precision).
    t1 = Tier(
        1,
        "High-delta skill ablation",
        "Where do skills help most? (avg +0.32 in pilot)",
    )
    for task in HIGH_DELTA:
        for condition in ["no-skill", "with-skill"]:
            for model in all_models:
                for seed in range(1, seeds + 1):
                    t1.runs.append(
                        dict(
                            task=task,
                            condition=condition,
                            model=model,
                            schema="native",
                            trial=seed,
                        )
                    )
    tiers.append(t1)

    # ── Tier 2: Skill-hurts investigation — reduced model set ──────────
    # Confirm the OASIS skill-hurts pattern and sepsis3 failure are real.
    # Both model tiers to confirm skill-hurts pattern across capability levels.
    t2 = Tier(
        2,
        "Skill-hurts investigation",
        "Are skills harmful for OASIS/sepsis3? (avg -0.20 in pilot)",
    )
    for task in SKILL_HURTS:
        for condition in ["no-skill", "with-skill"]:
            for model in model_plan.hurts_models:
                for seed in range(1, seeds + 1):
                    t2.runs.append(
                        dict(
                            task=task,
                            condition=condition,
                            model=model,
                            schema="native",
                            trial=seed,
                        )
                    )
    tiers.append(t2)

    # ── Tier 3: Flat/ceiling tasks — lighter-seed primary model set ────
    # Skills had negligible effect on Opus.  Still need model-scaling data
    # (weaker models might benefit where frontier doesn't), but lower variance means
    # 3 seeds gives adequate confidence intervals.
    flat_seeds = min(seeds, 3)
    t3 = Tier(
        3,
        "Flat tasks (ceiling confirmation)",
        "Do weaker models benefit from skills on tasks Opus aced?",
    )
    for task in FLAT:
        for condition in ["no-skill", "with-skill"]:
            for model in all_models:
                for seed in range(1, flat_seeds + 1):
                    t3.runs.append(
                        dict(
                            task=task,
                            condition=condition,
                            model=model,
                            schema="native",
                            trial=seed,
                        )
                    )
    tiers.append(t3)

    # ── Tier 4: KDIGO-48h rerun — clean rerun on the primary model set ─
    # Auth failure in pilot; needs clean data.
    t4 = Tier(4, "KDIGO-48h rerun", "Fill gap from auth failure in pilot")
    for condition in ["no-skill", "with-skill"]:
        for model in all_models:
            for seed in range(1, seeds + 1):
                t4.runs.append(
                    dict(
                        task="mimic-kdigo-48h",
                        condition=condition,
                        model=model,
                        schema="native",
                        trial=seed,
                    )
                )
    tiers.append(t4)

    # ── Tier 5: Contamination analysis ──────────────────────────────────
    # Raw-mode tasks with obfuscated/restructured DBs.  One contamination model,
    # no-skill only — isolates memorization from skill knowledge.
    t5 = Tier(
        5,
        "Contamination analysis",
        "Is no-skill performance driven by MIMIC memorization?",
    )
    for task in CONTAMINATION_TASKS:
        for schema in ["obfuscated", "restructured"]:
            for seed in range(1, seeds + 1):
                t5.runs.append(
                    dict(
                        task=task,
                        condition="no-skill",
                        model=model_plan.contamination_models[0],
                        schema=schema,
                        trial=seed,
                    )
                )
    tiers.append(t5)

    # ── Tier 6: Skill noise (with-skill-all) ────────────────────────────
    # Inject ALL skills on expert tasks.  Given that single-skill already
    # hurts on OASIS/sepsis3, this tests whether noise compounds.
    t6 = Tier(
        6,
        "Skill noise (all skills injected)",
        "Does injecting irrelevant skills compound the harm?",
    )
    noise_tasks = sorted(set(EXPERT_TASKS + COMPOSITIONAL_TASKS))
    for task in noise_tasks:
        for seed in range(1, seeds + 1):
            t6.runs.append(
                dict(
                    task=task,
                    condition="with-skill-all",
                    model=model_plan.noise_models[0],
                    schema="native",
                    trial=seed,
                )
            )
    tiers.append(t6)

    return tiers


def _build_provider_comparison_tiers(
    seeds: int = SEEDS, agent: str = "claude"
) -> list[Tier]:
    """Build a sparse matrix for non-primary provider comparison.

    This profile is intentionally not powered as a standalone benchmark-wide
    comparison.  It samples tasks that represent the main failure modes and
    skill-effect regimes so other providers can be used as external-validity
    checks while the statistical burden stays on the GPT-backed powered matrix.
    """
    model_plan = _model_plan_for_agent(agent)
    comparison_seeds = seeds
    contamination_seeds = seeds

    sentinel_tasks = [
        "mimic-urine-output-rate-raw",  # largest pilot skill delta; rolling windows
        "mimic-ventilation",  # string matching + temporal episode logic
        "mimic-creatinine-baseline-raw",  # decision tree + ICD lookup
        "mimic-suspicion-infection",  # asymmetric temporal matching
        "mimic-vasopressor-equivalents-raw",  # dose/unit conversion
        "mimic-oasis-24h",  # skill-hurts sentinel
        "mimic-sepsis3-raw",  # compositional expert task
        "mimic-sofa-24h-raw",  # canonical flat/expert severity-score task
    ]

    tiers: list[Tier] = []

    t1 = Tier(
        1,
        "Provider comparison sentinel",
        "Do external providers show the same skill-effect pattern on sentinel tasks?",
    )
    for task in sentinel_tasks:
        for condition in ["no-skill", "with-skill"]:
            for model in model_plan.primary_models:
                for seed in range(1, comparison_seeds + 1):
                    t1.runs.append(
                        dict(
                            task=task,
                            condition=condition,
                            model=model,
                            schema="native",
                            trial=seed,
                        )
                    )
    tiers.append(t1)

    contamination_tasks = [
        task
        for task in [
            "mimic-sofa-24h-raw",
            "mimic-kdigo-48h-raw",
            "mimic-oasis-24h-raw",
        ]
        if task in CONTAMINATION_TASKS
    ]
    if contamination_tasks:
        t2 = Tier(
            2,
            "Provider contamination sentinel",
            "Does no-skill external-provider performance survive schema perturbation?",
        )
        for task in contamination_tasks:
            for schema in ["obfuscated", "restructured"]:
                for seed in range(1, contamination_seeds + 1):
                    t2.runs.append(
                        dict(
                            task=task,
                            condition="no-skill",
                            model=model_plan.contamination_models[0],
                            schema=schema,
                            trial=seed,
                        )
                    )
        tiers.append(t2)

    return tiers


# ── Existing result detection ────────────────────────────────────────────────


def _cell_key(
    task: str,
    condition: str,
    model: str,
    schema: str,
    resolved_reasoning_effort: str,
) -> str:
    """Return the scheduling cell key used for skip-existing accounting."""
    return f"{task}|{condition}|{model}|{schema}|{resolved_reasoning_effort}"


def _scan_existing(results_root: Path) -> dict[str, set[int]]:
    """Scan results/ for completed runs. Returns {run_key: completed_trials}.

    A "completed" run must be publishable, pass the isolation/lint checks, and
    have a recorded reward. Tracking exact trial ids prevents interrupted
    resumes from duplicating already completed seed labels without letting
    contaminated or failed runs satisfy a paper campaign.
    """
    completed: dict[str, set[int]] = defaultdict(set)
    if not results_root.exists():
        return completed

    for result_file in results_root.rglob("result.json"):
        try:
            data = json.loads(result_file.read_text())
        except (json.JSONDecodeError, OSError):
            continue

        task = data.get("task", "")
        condition = data.get("condition", "")
        model = data.get("model", "")
        schema = data.get("schema", "native")
        resolved_reasoning_effort = data.get(
            "resolved_reasoning_effort",
            data.get("reasoning_effort", "legacy-default"),
        )

        # Normalize condition names from older batch runs
        if condition.startswith("_batch-"):
            condition = condition.replace("_batch-", "")

        if not _is_publishable_completed_result(data):
            continue
        try:
            trial = int(data.get("trial"))
        except (TypeError, ValueError):
            continue

        key = _cell_key(task, condition, model, schema, resolved_reasoning_effort)
        completed[key].add(trial)

    return completed


def _is_publishable_completed_result(data: dict) -> bool:
    """Return whether a result is valid enough to satisfy --skip-existing."""
    if data.get("test_results", {}).get("reward") is None:
        return False
    if data.get("publishable") is not True:
        return False
    if data.get("agent_result", {}).get("failure_reason"):
        return False
    if data.get("filesystem_canary", {}).get("passed") is not True:
        return False
    if data.get("contamination_lint", {}).get("passed") is not True:
        return False
    return True


def _filter_existing(
    runs: list[dict],
    existing: dict[str, set[int]],
    resolved_reasoning_effort: str = PROVIDER_DEFAULT_REASONING,
) -> list[dict]:
    """Remove runs whose exact scheduling cell and trial already completed."""
    filtered = []
    for run in runs:
        key = _cell_key(
            run["task"],
            run["condition"],
            run["model"],
            run["schema"],
            resolved_reasoning_effort,
        )
        if int(run["trial"]) not in existing.get(key, set()):
            filtered.append(run)

    return filtered


# ── Execution ────────────────────────────────────────────────────────────────


def _run_tier(
    tier: Tier,
    parallel: int,
    skip_existing: bool,
    dry_run: bool,
    no_isolation: bool,
    agent: str = "claude",
    reasoning_effort: str = BENCHMARK_REASONING_EFFORT,
    resolved_reasoning_effort: str = PROVIDER_DEFAULT_REASONING,
    results_root: Path | None = None,
    delay_between_runs_seconds: int = 0,
    max_retries: int = 0,
    retry_delay_seconds: int = 15,
    wait_on_claude_rate_limit: bool = False,
    docker_execution: bool = True,
) -> None:
    """Execute a single tier."""
    runs = tier.runs
    results_root = results_root or RESULTS_DIR

    if skip_existing:
        existing = _scan_existing(results_root)
        original = len(runs)
        runs = _filter_existing(runs, existing, resolved_reasoning_effort)
        skipped = original - len(runs)
        if skipped:
            print(f"  Skipping {skipped} runs with sufficient existing data")

    if not runs:
        print("  Nothing to run — all cells satisfied.\n")
        return

    # Group by (condition, model, schema) since run.py operates on one
    # condition+model+schema at a time.
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for run in runs:
        key = (run["condition"], run["model"], run["schema"])
        groups[key].append(run)

    for (condition, model, schema), group_runs in sorted(groups.items()):
        task_trials: dict[str, list[int]] = defaultdict(list)
        for r in group_runs:
            task_trials[r["task"]].append(r["trial"])

        # Build unique task list preserving order
        tasks = list(dict.fromkeys(r["task"] for r in group_runs))

        label = f"condition={condition} model={model} schema={schema}"
        print(f"\n  {label}")
        print(f"  Tasks: {len(tasks)}, Runs: {len(group_runs)}")

        if dry_run:
            for task in tasks:
                trials = sorted(task_trials[task])
                print(f"    {task:<40s} seeds {trials}")
            continue

        # Build the run.py command.  We invoke run.py per-group because it
        # handles --seeds and --parallel internally.

        if parallel > 1:
            _run_group_parallel(
                group_runs,
                condition,
                model,
                schema,
                parallel,
                no_isolation,
                agent,
                reasoning_effort,
                results_root,
                max_retries=max_retries,
                retry_delay_seconds=retry_delay_seconds,
                wait_on_claude_rate_limit=wait_on_claude_rate_limit,
                docker_execution=docker_execution,
            )
        else:
            _run_group_sequential(
                group_runs,
                condition,
                model,
                schema,
                no_isolation,
                agent,
                reasoning_effort,
                results_root,
                delay_between_runs_seconds=delay_between_runs_seconds,
                max_retries=max_retries,
                retry_delay_seconds=retry_delay_seconds,
                wait_on_claude_rate_limit=wait_on_claude_rate_limit,
                docker_execution=docker_execution,
            )


def _run_group_sequential(
    runs: list[dict],
    condition: str,
    model: str,
    schema: str,
    no_isolation: bool,
    agent: str = "claude",
    reasoning_effort: str = BENCHMARK_REASONING_EFFORT,
    results_root: Path | None = None,
    delay_between_runs_seconds: int = 0,
    max_retries: int = 0,
    retry_delay_seconds: int = 15,
    wait_on_claude_rate_limit: bool = False,
    docker_execution: bool = True,
) -> None:
    """Run a group of runs sequentially."""
    from run import run_single_task

    isolated = not no_isolation
    results_root = results_root or RESULTS_DIR
    for i, run in enumerate(runs, 1):
        print(f"\n  [{i}/{len(runs)}] {run['task']} trial={run['trial']}")
        try:
            if docker_execution:
                result = _run_via_bench(
                    run,
                    condition,
                    model,
                    schema,
                    agent,
                    results_root,
                    reasoning_effort=reasoning_effort,
                    max_retries=max_retries,
                    retry_delay_seconds=retry_delay_seconds,
                    wait_on_claude_rate_limit=wait_on_claude_rate_limit,
                )
            else:
                result = run_single_task(
                    run["task"],
                    condition,
                    agent,
                    model,
                    run["trial"],
                    verbose=False,
                    isolated=isolated,
                    schema=schema,
                    results_root=results_root,
                    max_retries=max_retries,
                    retry_delay_seconds=retry_delay_seconds,
                    wait_on_claude_rate_limit=wait_on_claude_rate_limit,
                    reasoning_effort=reasoning_effort,
                )
            reward = result.get("test_results", {}).get("reward", 0.0)
            elapsed = result.get("agent_result", {}).get("elapsed_seconds", 0)
            error = result.get("error")
            if error:
                print(f"    -> ERROR: {error}")
            else:
                print(f"    -> reward={reward:.4f} ({elapsed:.0f}s)")
            if delay_between_runs_seconds > 0 and i < len(runs):
                print(f"    -> sleeping {delay_between_runs_seconds}s")
                import time

                time.sleep(delay_between_runs_seconds)
        except Exception as e:
            print(f"    -> ERROR: {e}")


def _run_group_parallel(
    runs: list[dict],
    condition: str,
    model: str,
    schema: str,
    max_workers: int,
    no_isolation: bool,
    agent: str = "claude",
    reasoning_effort: str = BENCHMARK_REASONING_EFFORT,
    results_root: Path | None = None,
    max_retries: int = 0,
    retry_delay_seconds: int = 15,
    wait_on_claude_rate_limit: bool = False,
    docker_execution: bool = True,
) -> None:
    """Run a group of runs in parallel."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from run import run_single_task

    isolated = not no_isolation
    results_root = results_root or RESULTS_DIR
    done = 0
    total = len(runs)

    def _run_one(run: dict) -> dict:
        try:
            if docker_execution:
                return _run_via_bench(
                    run,
                    condition,
                    model,
                    schema,
                    agent,
                    results_root,
                    reasoning_effort=reasoning_effort,
                    max_retries=max_retries,
                    retry_delay_seconds=retry_delay_seconds,
                    wait_on_claude_rate_limit=wait_on_claude_rate_limit,
                )
            return run_single_task(
                run["task"],
                condition,
                agent,
                model,
                run["trial"],
                verbose=False,
                isolated=isolated,
                schema=schema,
                results_root=results_root,
                max_retries=max_retries,
                retry_delay_seconds=retry_delay_seconds,
                wait_on_claude_rate_limit=wait_on_claude_rate_limit,
                reasoning_effort=reasoning_effort,
            )
        except Exception as e:
            return {
                "task": run["task"],
                "trial": run["trial"],
                "test_results": {"reward": 0.0},
                "error": str(e),
            }

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_run_one, r): r for r in runs}
        for future in as_completed(futures):
            run = futures[future]
            done += 1
            try:
                result = future.result()
                reward = result.get("test_results", {}).get("reward", 0.0)
                elapsed = result.get("agent_result", {}).get("elapsed_seconds", 0)
                error = result.get("error")
                if error:
                    print(
                        f"  [{done}/{total}] {run['task']} t{run['trial']} -> "
                        f"ERROR: {error}"
                    )
                else:
                    print(
                        f"  [{done}/{total}] {run['task']} t{run['trial']} -> "
                        f"reward={reward:.4f} ({elapsed:.0f}s)"
                    )
            except Exception as e:
                print(f"  [{done}/{total}] {run['task']} t{run['trial']} -> ERROR: {e}")


# ── Display ──────────────────────────────────────────────────────────────────


def _print_matrix_summary(
    tiers: list[Tier],
    skip_existing: bool,
    results_root: Path | None = None,
    resolved_reasoning_effort: str = PROVIDER_DEFAULT_REASONING,
) -> None:
    """Print a human-readable summary of the experiment matrix."""
    results_root = results_root or RESULTS_DIR
    existing = _scan_existing(results_root) if skip_existing else {}

    grand_total = 0
    grand_skip = 0

    print("\n" + "=" * 78)
    print("M4BENCH EXPERIMENT MATRIX")
    print("=" * 78)
    print(f"Results root: {results_root}")

    for tier in tiers:
        runs = tier.runs
        skipped = 0
        if skip_existing:
            filtered = _filter_existing(runs, existing, resolved_reasoning_effort)
            skipped = len(runs) - len(filtered)
            runs = filtered

        grand_total += len(runs)
        grand_skip += skipped

        # Count unique cells
        cells = set()
        for r in tier.runs:
            cells.add((r["task"], r["condition"], r["model"], r["schema"]))

        models = sorted(set(r["model"] for r in tier.runs))
        conditions = sorted(set(r["condition"] for r in tier.runs))
        schemas = sorted(set(r["schema"] for r in tier.runs))
        tasks = sorted(set(r["task"] for r in tier.runs))

        print(f"\nTier {tier.number}: {tier.name}")
        print(f"  Question: {tier.question}")
        print(f"  Models: {', '.join(models)}")
        print(f"  Conditions: {', '.join(conditions)}")
        print(f"  Schemas: {', '.join(schemas)}")
        seeds_per = max(len(tier.runs) // len(cells), 1) if cells else 0
        print(
            f"  Tasks: {len(tasks)} | Cells: {len(cells)} | "
            f"Runs: {len(tier.runs)} ({seeds_per} seeds each)"
        )
        if skipped:
            print(f"  Skippable: {skipped} (already have data) -> {len(runs)} new runs")

    print(f"\n{'─' * 78}")
    total_naive = (
        len(ALL_TASKS) * 3 * 3 * 3 * SEEDS
    )  # tasks x conditions x models x schemas x seeds
    print(
        f"Total runs:  {grand_total}"
        + (f"  (skipping {grand_skip} with existing data)" if grand_skip else "")
    )
    print(f"Naive full product would be: {total_naive}")
    print(f"Efficiency: {grand_total / total_naive:.0%} of naive product")
    print("=" * 78)


# ── Main ─────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Smart experiment matrix for M4Bench",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--tier",
        nargs="+",
        default=["all"],
        help="Tiers to run (e.g., 1 2 3, or 'all')",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show matrix without running"
    )
    parser.add_argument("--parallel", type=int, default=1, help="Max concurrent runs")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip exact task/model/condition/schema/trial runs that already have result.json",
    )
    parser.add_argument(
        "--no-isolation",
        action="store_true",
        help="Disable isolation (local debugging ONLY)",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print matrix summary and exit (implies --dry-run)",
    )
    parser.add_argument(
        "--profile",
        choices=["powered", "provider-comparison"],
        default="powered",
        help=(
            "Matrix profile: powered is the GPT-primary campaign; "
            "provider-comparison is a sparse external-provider sentinel set"
        ),
    )
    parser.add_argument(
        "--agent",
        default="codex",
        help="Agent CLI to use (claude, codex, gemini, pi-ollama)",
    )
    parser.add_argument(
        "--reasoning-effort",
        choices=REASONING_EFFORT_CHOICES,
        default=BENCHMARK_REASONING_EFFORT,
        help=(
            "Reasoning policy. auto pins Codex/Claude to medium and leaves "
            "Gemini at provider-default; default leaves each CLI/provider default"
        ),
    )
    parser.add_argument(
        "--seeds",
        type=int,
        default=SEEDS,
        help=f"Seeds per cell (default: {SEEDS})",
    )
    parser.add_argument(
        "--results-root",
        help="Directory for run outputs and skip-existing scans",
    )
    parser.add_argument(
        "--driver",
        choices=["docker", "local"],
        default="docker",
        help="Execution backend: docker uses bench.sh for publishable runs; local is debugging only",
    )
    parser.add_argument(
        "--delay-between-runs-seconds",
        type=int,
        default=0,
        help="Sleep between sequential runs",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=0,
        help="Retry failed runs this many times",
    )
    parser.add_argument(
        "--retry-delay-seconds",
        type=int,
        default=15,
        help="Seconds to wait before retrying a failed run",
    )
    parser.add_argument(
        "--wait-on-claude-rate-limit",
        action="store_true",
        help="When Claude hits a five-hour limit, wait until reset and retry",
    )
    args = parser.parse_args()

    docker_execution = args.driver == "docker"
    if args.no_isolation and docker_execution:
        parser.error("--no-isolation is only valid with --driver local")

    if args.agent == "claude" and args.parallel > 1:
        print(
            "Warning: Claude subscription runs are much more reliable with --parallel 1."
        )
    if args.delay_between_runs_seconds and args.parallel > 1:
        print(
            "Warning: --delay-between-runs-seconds applies only to sequential execution."
        )
    if (
        docker_execution
        and args.results_root is None
        and not (args.summary or args.dry_run)
    ):
        parser.error("--results-root is required for docker-backed campaigns")

    _classify_tasks()
    seeds = args.seeds
    tiers = build_tiers(seeds=seeds, agent=args.agent, profile=args.profile)
    results_root = resolve_results_root(args.results_root)
    try:
        resolved_reasoning_effort = _resolve_reasoning_effort(
            args.agent, args.reasoning_effort
        )
    except ValueError as e:
        parser.error(str(e))

    if args.summary or args.dry_run:
        print(
            f"Reasoning: {resolved_reasoning_effort}"
            f" (requested: {args.reasoning_effort})"
        )
        _print_matrix_summary(
            tiers,
            args.skip_existing,
            results_root,
            resolved_reasoning_effort,
        )

    if args.summary:
        return

    # Select tiers
    if "all" in args.tier:
        selected = tiers
    else:
        tier_nums = {int(t) for t in args.tier}
        selected = [t for t in tiers if t.number in tier_nums]
        if not selected:
            print(f"No tiers matched: {args.tier}")
            sys.exit(1)

    if args.dry_run:
        # Already printed summary; show per-tier details
        for tier in selected:
            print(f"\n{'─' * 78}")
            print(f"Tier {tier.number}: {tier.name} ({tier.total} runs)")
            _run_tier(
                tier,
                args.parallel,
                args.skip_existing,
                dry_run=True,
                no_isolation=args.no_isolation,
                agent=args.agent,
                reasoning_effort=args.reasoning_effort,
                resolved_reasoning_effort=resolved_reasoning_effort,
                results_root=results_root,
                delay_between_runs_seconds=args.delay_between_runs_seconds,
                max_retries=args.max_retries,
                retry_delay_seconds=args.retry_delay_seconds,
                wait_on_claude_rate_limit=args.wait_on_claude_rate_limit,
                docker_execution=docker_execution,
            )
        return

    # Execute
    for tier in selected:
        print(f"\n{'━' * 78}")
        print(f"TIER {tier.number}: {tier.name.upper()}")
        print(f"Question: {tier.question}")
        print(f"{'━' * 78}")
        _run_tier(
            tier,
            args.parallel,
            args.skip_existing,
            dry_run=False,
            no_isolation=args.no_isolation,
            agent=args.agent,
            reasoning_effort=args.reasoning_effort,
            resolved_reasoning_effort=resolved_reasoning_effort,
            results_root=results_root,
            delay_between_runs_seconds=args.delay_between_runs_seconds,
            max_retries=args.max_retries,
            retry_delay_seconds=args.retry_delay_seconds,
            wait_on_claude_rate_limit=args.wait_on_claude_rate_limit,
            docker_execution=docker_execution,
        )

    print("\nDone.")


if __name__ == "__main__":
    main()
