"""M4Bench evaluation harness.

Orchestrates: task setup -> agent invocation -> output collection -> test execution.

Isolation is ON by default, but release-grade runs still require Docker via
`benchmark/bench.sh`. Outside Docker, local runs are useful for debugging and
anomaly investigation only. Pass --no-isolation for fully local debugging
(also not publishable).

Usage:
    # Run a single task
    python benchmark/run.py --task mimic-sirs-24h --condition with-skill --agent claude

    # Run all variants of a task family
    python benchmark/run.py --family sofa --condition no-skill --agent claude

    # Run all tasks
    python benchmark/run.py --task all --condition with-skill --agent claude --model opus

    # List available tasks
    python benchmark/run.py --list

    # Local debugging only (disables isolation — NOT for publishable results)
    python benchmark/run.py --task mimic-sirs-24h --condition no-skill --agent claude --no-isolation
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import gzip
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
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
AGENT_USER = "benchagent"
CONTAINER_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
M4_DATA_VIEW_PATTERN = re.compile(r"'/[^']*/m4_data/")
EXTERNAL_NETWORK_COMMAND_PATTERN = re.compile(
    r"\b(curl|wget)\b|https?://|\burllib\b|requests\.get|urlopen|duckduckgo|github\.com",
    re.IGNORECASE,
)
SENSITIVE_CONTENT_PATTERNS = (
    "/private-benchmark",
    "/benchmark/ground_truth",
    "/benchmark/tasks",
    "/benchmark/agent_db",
    "/benchmark/results",
    "/benchmark/lib/dictionary.json",
    "/tmp/clinskillsbench/_db_cache",
    "/host-auth",
    "/claude-auth",
    "ground_truth/",
    "ground_truth.csv",
    "ground_truth.sql",
    "dictionary.json",
)
SECRET_CONTENT_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9][A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bsk-ant-[A-Za-z0-9][A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
    re.compile(r"\bgh[pousr]_[0-9A-Za-z]{20,}\b"),
    re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{20,}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(
        r'"(?:access_token|refresh_token|id_token|api[_-]?key)"\s*:\s*"[^"]{12,}"',
        re.IGNORECASE,
    ),
)
SECRET_ENV_KEYS = {
    "ANTHROPIC_API_KEY",
    "CODEX_API_KEY",
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
}
ALLOWED_LLM_API_HOSTS = {
    "api.anthropic.com",
    "mcp-proxy.anthropic.com",
    "api.openai.com",
    "auth.openai.com",
    "chatgpt.com",
    "cloudcode-pa.googleapis.com",
    "generativelanguage.googleapis.com",
    "http-intake.logs.us5.datadoghq.com",
    "oauth2.googleapis.com",
    "play.googleapis.com",
    "platform.claude.com",
}
ALLOWED_LLM_API_HOST_SUFFIXES = (
    ".chatgpt.com",
    ".auth.openai.com",
)
LEAK_CANARY_PATHS = (
    "/benchmark/ground_truth",
    "/benchmark/tasks",
    "/benchmark/agent_db",
    "/benchmark/results",
    "/tmp/clinskillsbench/_db_cache",
    "/host-auth",
    "/claude-auth",
    "/benchmark/lib/dictionary.json",
)
FILESYSTEM_CANARY_CHECKS = (
    ("benchmark_ground_truth", "test ! -r /benchmark/ground_truth"),
    ("benchmark_tasks", "test ! -r /benchmark/tasks"),
    ("benchmark_agent_db", "test ! -r /benchmark/agent_db"),
    ("out_staging", "test ! -r /out"),
    ("benchmark_results", "test ! -r /benchmark/results"),
    ("db_cache", "test ! -r /tmp/clinskillsbench/_db_cache"),
    ("host_auth", "test ! -r /host-auth"),
    ("claude_auth", "test ! -e /claude-auth || test ! -r /claude-auth"),
    ("obfuscation_dictionary", "test ! -r /benchmark/lib/dictionary.json"),
    (
        "previous_run_marker",
        "test ! -e /tmp/clinskillsbench/previous_run_marker",
    ),
)
DATABASE_ARTIFACT_SUFFIXES = (
    ".duckdb",
    ".duckdb.wal",
    ".db",
    ".sqlite",
    ".sqlite-shm",
    ".sqlite-wal",
)
RESULT_EXPORT_SKIP_DIRS = {
    ".cache",
    ".claude",
    ".codex",
    ".gemini",
    ".m4bench",
    ".pi",
    "__pycache__",
    "_home",
}
RESULT_EXPORT_MAX_FILE_BYTES = 50 * 1024 * 1024
REQUIRED_RESULT_ARTIFACTS = {
    "egress.jsonl",
    "instruction.md",
    "output.csv",
    "result.json",
    "trace.jsonl",
}
TEXT_LINT_SUFFIXES = {
    ".csv",
    ".json",
    ".jsonl",
    ".md",
    ".py",
    ".r",
    ".R",
    ".sh",
    ".sql",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
AUTH_ARTIFACT_RELATIVE_PATHS = {
    ".codex/auth.json",
}

# Tools to deny in isolated mode — defence-in-depth on top of iptables.
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

# Agent CLI commands.
# Skills are injected into an agent-specific directory inside the workdir
# (for example, .claude/skills or .codex/skills) so each parallel run sees
# only its own skills.
AGENT_COMMANDS = {
    "claude": {
        "cmd": [
            "claude",
            "-p",
            "--allowedTools",
            "Bash(*),Read,Write,Glob,Grep,Edit",
        ],
        "skill_dir": ".claude/skills",
        "json_trace": True,
    },
    "codex": {
        "cmd": [
            "codex",
            "exec",
            "--skip-git-repo-check",
            "-c",
            'web_search="disabled"',
            "-c",
            "tools.web_search=false",
            "-c",
            'sandbox_mode="workspace-write"',
            "-c",
            (
                'developer_instructions="M4Bench isolation: use only local files, '
                "the provided DuckDB database, and injected skills. Do not use web "
                "search, web fetch, curl, wget, package installation, or any other "
                'external network source."'
            ),
            "--disable",
            "plugins",
        ],
        "skill_dir": ".codex/skills",
        "json_trace": True,
    },
    "gemini": {
        "cmd": ["gemini", "--approval-mode", "yolo", "--skip-trust", "-p"],
        "skill_dir": ".gemini/skills",
        "json_trace": False,
    },
    "pi-ollama": {
        "cmd": [
            "pi",
            "--provider",
            "ollama",
            "--no-context-files",
            "--no-themes",
            "--no-prompt-templates",
            "--no-extensions",
            "--skill",
            ".pi/skills",
            "-p",
        ],
        "skill_dir": ".pi/skills",
        "json_trace": False,
    },
}

AGENT_HOME_SEEDS = {
    "claude": [
        ".claude.json",
        ".claude/.credentials.json",
        ".claude/credentials.json",
    ],
    "codex": [".codex/auth.json"],
    "gemini": [
        ".gemini/oauth_creds.json",
        ".gemini/google_accounts.json",
        ".gemini/state.json",
        ".gemini/settings.json",
        ".gemini/installation_id",
    ],
    "pi-ollama": [".pi/agent/models.json"],
}

CLAUDE_LOGIN_AUTH_SEEDS = [
    ".claude.json",
    ".claude/.credentials.json",
    ".claude/credentials.json",
]

CLAUDE_MEMORY_ESCAPE_PREFIXES = (
    "/claude-auth",
    "/home/benchagent",
    "/root",
)

REASONING_EFFORT_CHOICES = (
    "auto",
    "default",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)
BENCHMARK_REASONING_EFFORT = "auto"
PROVIDER_DEFAULT_REASONING = "provider-default"
AGENT_REASONING_EFFORTS = {
    "claude": {"low", "medium", "high", "xhigh", "max"},
    "codex": {"minimal", "low", "medium", "high", "xhigh"},
}


def _resolve_reasoning_effort(agent_name: str, reasoning_effort: str | None) -> str:
    """Resolve benchmark reasoning policy to the setting applied to an agent."""
    requested = reasoning_effort or BENCHMARK_REASONING_EFFORT
    if requested == "auto":
        if agent_name in ("claude", "codex"):
            return "medium"
        return PROVIDER_DEFAULT_REASONING
    if requested == "default":
        return PROVIDER_DEFAULT_REASONING

    allowed = AGENT_REASONING_EFFORTS.get(agent_name)
    if not allowed:
        raise ValueError(
            f"{agent_name} does not support named reasoning effort in this harness; "
            "use --reasoning-effort auto or default"
        )
    if requested not in allowed:
        allowed_values = ", ".join(sorted(allowed))
        raise ValueError(
            f"{agent_name} does not support reasoning effort '{requested}'. "
            f"Supported values: auto, default, {allowed_values}"
        )
    return requested


def _reasoning_args_for_agent(
    agent_name: str, resolved_reasoning_effort: str
) -> list[str]:
    """Return CLI args that apply an already-resolved reasoning effort."""
    if resolved_reasoning_effort == PROVIDER_DEFAULT_REASONING:
        return []
    if agent_name == "claude":
        return ["--effort", resolved_reasoning_effort]
    if agent_name == "codex":
        return ["-c", f'model_reasoning_effort="{resolved_reasoning_effort}"']
    return []


def resolve_results_root(results_root: str | None = None) -> Path:
    """Resolve the output root for benchmark artifacts."""
    if results_root:
        return Path(results_root).expanduser().resolve()
    return RESULTS_DIR.resolve()


def _running_in_container() -> bool:
    """Best-effort check for Docker/container execution."""
    return Path("/.dockerenv").exists()


def _agent_container_enabled() -> bool:
    """Return True when agents should run in a minimal Docker container."""
    return os.environ.get("M4BENCH_AGENT_CONTAINER") == "1"


def _publishable_environment(
    isolated: bool, agent_name: str | None = None
) -> tuple[bool, str]:
    """Return whether the current run environment is release-eligible."""
    if not isolated:
        return False, "isolation disabled"
    if not _agent_container_enabled():
        return False, "agent-container isolation required"
    if os.environ.get("M4BENCH_ALLOW_OLLAMA") == "1":
        return False, "local Ollama host exception enabled"
    try:
        _agent_container_extra_mounts()
    except RuntimeError as exc:
        return False, f"invalid agent-container mounts: {exc}"
    return True, "agent-only Docker isolation active"


def ensure_results_manifest(results_root: Path) -> Path:
    """Create a manifest describing the provenance expectations for this root."""
    results_root.mkdir(parents=True, exist_ok=True)
    manifest_path = results_root / "campaign_manifest.json"
    if manifest_path.exists():
        return manifest_path

    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "results_root": str(results_root),
        "canonical_release_spec": str((BENCHMARK_ROOT / "README.md").resolve()),
        "publishable_run_requirements": [
            "run via benchmark/bench.sh inside Docker",
            "do not mix with legacy benchmark/results outputs",
            "treat local run.py executions as debugging only",
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return manifest_path


# ── Agent user isolation ───────────────────────────────────────────────────


def _resolve_agent_creds() -> tuple[int, int] | None:
    """Return (uid, gid) for the benchagent user, or None if unavailable.

    When running inside the Docker container, benchagent exists and the agent
    subprocess will run as this user.  Locally (outside Docker) the user
    won't exist and we fall back to the current user.
    """
    try:
        import pwd

        pw = pwd.getpwnam(AGENT_USER)
        return (pw.pw_uid, pw.pw_gid)
    except (KeyError, ImportError):
        return None


def _chown_recursive(path: Path, uid: int, gid: int) -> None:
    """Recursively change ownership of a directory tree."""
    for dirpath, _dirnames, filenames in os.walk(path):
        os.chown(dirpath, uid, gid)
        for filename in filenames:
            os.chown(os.path.join(dirpath, filename), uid, gid)


def _agent_visible_results_root(
    results_root: Path, *visible_roots: Path | None
) -> bool:
    """Return True when result staging is inside an agent-visible root."""
    resolved_results = results_root.resolve()
    for root in visible_roots:
        if root is None:
            continue
        try:
            resolved_results.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False


def run_filesystem_canary(
    agent_name: str,
    workdir: Path,
    run_home: Path | None,
    *,
    isolated: bool,
    enforce: bool,
) -> dict:
    """Verify sensitive benchmark paths are unreadable by the agent user."""
    env = _agent_process_env(agent_name, workdir, run_home) if run_home else None
    if isolated and _agent_container_enabled():
        failures_path = workdir / ".m4bench" / "filesystem_canary_failures.txt"
        failures_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "set -euo pipefail",
            "failures=()",
            "check() {",
            '  local name="$1"',
            '  local shell_check="$2"',
            '  if ! bash -lc "$shell_check"; then failures+=("$name"); fi',
            "}",
        ]
        for name, shell_check in FILESYSTEM_CANARY_CHECKS:
            lines.append(f"check {shlex.quote(name)} {shlex.quote(shell_check)}")
        lines.extend(
            [
                f"printf '%s\\n' \"${{failures[@]}}\" > {shlex.quote(str(failures_path))}",
                "exit 0",
            ]
        )
        completed = _run_agent_container_check(
            ["bash", "-lc", "\n".join(lines)],
            env=env,
            workdir=workdir,
            run_home=run_home,
        )
        if completed.returncode != 0:
            failures = ["agent_container_canary"]
        elif failures_path.exists():
            failures = [
                line.strip()
                for line in failures_path.read_text().splitlines()
                if line.strip()
            ]
        else:
            failures = ["agent_container_canary"]
        passed = not failures
        return {
            "passed": passed,
            "required": bool(enforce),
            "agent": agent_name,
            "agent_user": AGENT_USER,
            "checks": [name for name, _cmd in FILESYSTEM_CANARY_CHECKS],
            "failures": failures,
            "containerized_agent": True,
        }

    agent_creds = _resolve_agent_creds() if isolated else None

    if agent_creds:
        uid, gid = agent_creds
        _chown_recursive(workdir, uid, gid)
        if run_home:
            _chown_recursive(run_home, uid, gid)

    failures: list[str] = []
    for name, shell_check in FILESYSTEM_CANARY_CHECKS:
        completed = subprocess.run(
            ["bash", "-lc", shell_check],
            cwd=str(workdir),
            env=env,
            user=agent_creds[0] if agent_creds else None,
            group=agent_creds[1] if agent_creds else None,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if completed.returncode != 0:
            failures.append(name)

    passed = not failures
    required = bool(enforce)
    return {
        "passed": passed,
        "required": required,
        "agent": agent_name,
        "agent_user": AGENT_USER if agent_creds else None,
        "checks": [name for name, _cmd in FILESYSTEM_CANARY_CHECKS],
        "failures": failures,
    }


# ── Token refresh ──────────────────────────────────────────────────────────


def _load_jsonl_events(trace_path: str | Path) -> list[dict]:
    """Best-effort parse of a JSONL trace file."""
    path = Path(trace_path)
    if not path.exists():
        return []

    events: list[dict] = []
    for line in path.read_text(errors="ignore").splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def _load_egress_events(workdir: Path) -> list[dict]:
    """Load structured egress-proxy decisions, if Docker isolation produced them."""
    return _load_jsonl_events(workdir / "egress.jsonl")


def aggregate_token_usage(agent_name: str, trace_path: str | Path) -> dict:
    """Sum token usage from agent trace events.

    Returns a dict with input_tokens, cached_input_tokens, output_tokens, turns,
    and provider strings recovered from the trace. Empty values are returned
    when usage events are unavailable (e.g., agent CLI did not stream JSON).
    """
    summary = {
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "output_tokens": 0,
        "turns": 0,
        "model_strings": [],
    }
    seen_models: set[str] = set()
    events = _load_jsonl_events(trace_path)

    if agent_name == "codex":
        for event in events:
            if event.get("type") == "thread.started":
                model = event.get("model") or event.get("model_id")
                if isinstance(model, str) and model not in seen_models:
                    seen_models.add(model)
                    summary["model_strings"].append(model)
            elif event.get("type") == "turn.completed":
                usage = event.get("usage") or {}
                summary["turns"] += 1
                summary["input_tokens"] += int(usage.get("input_tokens") or 0)
                summary["cached_input_tokens"] += int(
                    usage.get("cached_input_tokens") or 0
                )
                summary["output_tokens"] += int(usage.get("output_tokens") or 0)

    elif agent_name == "claude":
        for event in events:
            usage = (
                event.get("usage") or (event.get("message") or {}).get("usage") or {}
            )
            if not usage:
                continue
            summary["input_tokens"] += int(usage.get("input_tokens") or 0)
            summary["output_tokens"] += int(usage.get("output_tokens") or 0)
            summary["cached_input_tokens"] += int(
                usage.get("cache_read_input_tokens") or 0
            )
            summary["turns"] += 1
            model = (event.get("message") or {}).get("model")
            if isinstance(model, str) and model not in seen_models:
                seen_models.add(model)
                summary["model_strings"].append(model)

    return summary


def _is_allowed_llm_host(host: str) -> bool:
    host = host.lower()
    return host in ALLOWED_LLM_API_HOSTS or any(
        host.endswith(suffix) for suffix in ALLOWED_LLM_API_HOST_SUFFIXES
    )


def _detect_disallowed_egress(workdir: Path) -> list[str]:
    """Return blocked or non-allowlisted network attempts from proxy logs."""
    violations: list[str] = []
    for event in _load_egress_events(workdir):
        host = str(event.get("host", "")).lower()
        port = event.get("port")
        allowed = event.get("allowed") is True
        if not allowed:
            violations.append(f"{host}:{port}")
        elif not _is_allowed_llm_host(host) or port != 443:
            violations.append(f"{host}:{port}")
    return sorted(set(violations))


def _extract_claude_rate_limit_reset_at(trace_path: str | Path) -> int | None:
    """Return the most recent Claude five-hour reset timestamp, if present."""
    reset_at = None
    for event in _load_jsonl_events(trace_path):
        if event.get("type") != "rate_limit_event":
            continue
        info = event.get("rate_limit_info", {})
        value = info.get("resetsAt")
        if isinstance(value, int):
            reset_at = value
    return reset_at


def _detect_agent_failure_reason(agent_name: str, agent_result: dict) -> str | None:
    """Classify recoverable agent failures for targeted retries."""
    text = " ".join(
        str(agent_result.get(key, "")) for key in ("stdout", "stderr")
    ).lower()

    if agent_name == "claude":
        if "invalid api key" in text or "fix external api key" in text:
            return "auth"

        for event in _load_jsonl_events(agent_result.get("trace_file", "")):
            if event.get("type") != "rate_limit_event":
                continue
            info = event.get("rate_limit_info", {})
            status = str(info.get("status", "")).lower()
            if status and status not in {"allowed", "allowed_warning"}:
                return "rate_limit"

        if agent_result.get("returncode") not in (0, None) and (
            "rate limit" in text
            or "usage limit" in text
            or re.search(r"(?<!\d)429(?!\d)", text)
        ):
            return "rate_limit"

    return None


def _detect_external_tool_use(trace_path: str | Path) -> list[str]:
    """Return disallowed external tools observed in a structured agent trace."""
    disallowed: list[str] = []
    for event in _load_jsonl_events(trace_path):
        item = event.get("item", {})
        candidates = [
            event.get("type", ""),
            item.get("type", ""),
            item.get("name", ""),
            item.get("tool", ""),
        ]
        text = " ".join(str(candidate).lower() for candidate in candidates)
        if "web_search" in text or "websearch" in text or "web_fetch" in text:
            disallowed.append("web_search")
        if item.get("type") == "command_execution":
            command = str(item.get("command", ""))
            if EXTERNAL_NETWORK_COMMAND_PATTERN.search(command):
                disallowed.append("external_network_command")
    return sorted(set(disallowed))


def _read_text_for_lint(path: Path) -> str | None:
    if path.suffix not in TEXT_LINT_SUFFIXES:
        return None
    try:
        return path.read_text(errors="ignore")
    except OSError:
        return None


def _is_auth_artifact_for_lint(rel_path: str) -> bool:
    """Return True for allowlisted provider auth seeds copied into the workdir."""
    return rel_path in AUTH_ARTIFACT_RELATIVE_PATHS


def _is_internal_artifact_for_lint(rel_path: str) -> bool:
    """Return True for provider/harness state that is not a scored artifact."""
    first_part = Path(rel_path).parts[0] if Path(rel_path).parts else ""
    return first_part in RESULT_EXPORT_SKIP_DIRS or _is_auth_artifact_for_lint(rel_path)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _agent_db_metadata(db_path: str | Path) -> dict:
    """Record the exact task DB used for auditability."""
    path = Path(db_path).resolve()
    return {
        "path": str(path),
        "sha256": _sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def lint_run_contamination(
    workdir: Path,
    task_name: str,
    *,
    run_id: str,
    prior_run_ids: set[str] | None = None,
) -> dict:
    """Fail runs whose agent-visible artifacts reference benchmark internals."""
    violations: list[str] = []
    prior_run_ids = prior_run_ids or set()

    for path in sorted(workdir.rglob("*")):
        if path.is_dir() or path.is_symlink():
            continue
        rel = path.relative_to(workdir).as_posix()
        if _is_internal_artifact_for_lint(rel):
            continue
        if _is_database_artifact(path):
            if path.name not in {"database.duckdb", "database.duckdb.wal"}:
                violations.append(f"{rel}: database artifact present")
            continue
        text = _read_text_for_lint(path)
        if text is None:
            continue
        for pattern in SENSITIVE_CONTENT_PATTERNS:
            if pattern in text:
                violations.append(f"{rel}: references {pattern}")
        for pattern in SECRET_CONTENT_PATTERNS:
            if pattern.search(text):
                violations.append(f"{rel}: contains token-shaped secret")
                break
        for prior_run_id in prior_run_ids:
            if prior_run_id != run_id and prior_run_id in text:
                violations.append(f"{rel}: references prior run {prior_run_id}")

    output_path = workdir / "output.csv"
    if output_path.exists():
        try:
            from evaluate import resolve_ground_truth

            gt_path = resolve_ground_truth(task_name)
            if _sha256_file(output_path) == _sha256_file(gt_path):
                violations.append("output.csv: byte-identical to ground truth")
        except Exception as exc:
            violations.append(f"ground truth hash check failed: {exc}")

    return {
        "passed": not violations,
        "violations": violations,
        "patterns": list(SENSITIVE_CONTENT_PATTERNS),
    }


def _sanitize_pytest_diagnostics(text: str) -> str:
    """Remove row-level truth examples and sensitive paths from stored results."""
    sanitized_lines: list[str] = []
    for line in str(text).splitlines():
        if "Examples:" in line:
            line = line.split("Examples:", 1)[0] + "Examples: [redacted]"
        for pattern in SENSITIVE_CONTENT_PATTERNS:
            if pattern in line:
                line = line.replace(pattern, "[redacted]")
        sanitized_lines.append(line)
    return "\n".join(sanitized_lines)


def _sanitize_agent_text(text: str, *, redact_all: bool = False) -> str:
    """Remove secrets and benchmark-internal paths before storing agent output."""
    if redact_all and text:
        return "[redacted: failed or contaminated run]"
    sanitized = str(text)
    for pattern in SENSITIVE_CONTENT_PATTERNS:
        sanitized = sanitized.replace(pattern, "[redacted]")
    for pattern in SECRET_CONTENT_PATTERNS:
        sanitized = pattern.sub("[redacted-secret]", sanitized)
    return sanitized


def sanitize_agent_result_for_storage(agent_result: dict, *, safe_run: bool) -> dict:
    """Return agent metadata without preserving leaked stdout/stderr."""
    sanitized = dict(agent_result)
    redact_all = not safe_run
    for key in ("stdout", "stderr"):
        if key in sanitized:
            sanitized[key] = _sanitize_agent_text(
                str(sanitized[key]), redact_all=redact_all
            )
    if not safe_run and sanitized.get("trace_file"):
        sanitized["trace_file"] = "[redacted: trace not exported for failed run]"
    return sanitized


def sanitize_test_results_for_storage(test_results: dict) -> dict:
    """Return result metrics with large/sensitive pytest diagnostics redacted."""
    sanitized = dict(test_results)
    for key in ("pytest_output", "pytest_stderr"):
        if key in sanitized:
            sanitized[key] = _sanitize_pytest_diagnostics(str(sanitized[key]))
    return sanitized


def _collect_prior_run_ids(results_root: Path, current_run_id: str) -> set[str]:
    run_ids: set[str] = set()
    if not results_root.exists():
        return run_ids
    for result_file in results_root.rglob("result.json"):
        try:
            data = json.loads(result_file.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        run_id = data.get("run_id")
        if isinstance(run_id, str) and run_id != current_run_id:
            run_ids.add(run_id)
    return run_ids


def validate_leak_canary_report(report: dict) -> dict:
    """Validate that the adversarial canary actually probed sensitive paths."""
    evidence = report.get("evidence", [])
    if not isinstance(evidence, list):
        evidence = []
    probed_paths = report.get("probed_paths", [])
    if not isinstance(probed_paths, list):
        probed_paths = []

    report_text = "\n".join(str(item) for item in [*evidence, *probed_paths])
    missing_paths = [path for path in LEAK_CANARY_PATHS if path not in report_text]
    return {
        "passed": not missing_paths,
        "required_paths": list(LEAK_CANARY_PATHS),
        "missing_paths": missing_paths,
    }


def _collect_claude_memory_paths(trace_path: str | Path) -> list[str]:
    """Return Claude memory paths reported in structured trace init events."""
    paths: list[str] = []
    for event in _load_jsonl_events(trace_path):
        memory_paths = event.get("memory_paths")
        if not isinstance(memory_paths, dict):
            continue
        for value in memory_paths.values():
            if isinstance(value, str):
                paths.append(value)
            elif isinstance(value, list):
                paths.extend(item for item in value if isinstance(item, str))
            elif isinstance(value, dict):
                paths.extend(item for item in value.values() if isinstance(item, str))
    return paths


def _path_is_under(path: str, root: Path) -> bool:
    """Return whether an absolute path string is contained by root."""
    try:
        resolved_path = Path(path).expanduser().resolve()
        resolved_root = root.expanduser().resolve()
        return os.path.commonpath([str(resolved_path), str(resolved_root)]) == str(
            resolved_root
        )
    except ValueError:
        return False


def _validate_claude_memory_paths(
    trace_path: str | Path, run_home: Path | None
) -> dict:
    """Validate that Claude memory paths stay inside the fresh per-run HOME."""
    paths = _collect_claude_memory_paths(trace_path)
    if run_home is None:
        return {
            "validated": False,
            "paths": paths,
            "violations": paths,
            "reason": "missing per-run HOME",
        }

    run_home_resolved = run_home.resolve()
    violations = []
    for path in paths:
        escaped_prefix = any(
            path == prefix or path.startswith(prefix + "/")
            for prefix in CLAUDE_MEMORY_ESCAPE_PREFIXES
        )
        if escaped_prefix or not _path_is_under(path, run_home_resolved):
            violations.append(path)

    return {
        "validated": bool(paths) and not violations,
        "paths": paths,
        "violations": violations,
        "reason": "" if paths else "no Claude memory paths found in trace",
    }


# ── Isolated workdir setup ──────────────────────────────────────────────────


def _create_isolated_settings(workdir: Path) -> Path:
    """Write a .claude/settings.json in the workdir that enforces the sandbox hook."""
    hook_path = SANDBOX_HOOK
    if _agent_container_enabled():
        runtime_dir = workdir / ".m4bench"
        runtime_dir.mkdir(exist_ok=True)
        hook_path = runtime_dir / "sandbox_hook.py"
        shutil.copy2(SANDBOX_HOOK, hook_path)

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
                            "command": f"python3 {hook_path} {workdir}",
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
    """Find the exact task-specific agent DB for a task and schema condition."""
    from lib.db import _db_prefix, _task_key

    task_key = _task_key(task_name)
    db_prefix = _db_prefix(task_name)
    if schema == "native":
        task_db = AGENT_DB_DIR / f"{db_prefix}_{task_key}.duckdb"
    else:
        # obfuscated or restructured (MIMIC-IV only)
        task_db = AGENT_DB_DIR / f"{schema}_{task_key}.duckdb"
    if not task_db.exists():
        raise FileNotFoundError(
            f"Exact task DB not found for {task_name}/{schema}: {task_db}. "
            f"Run: python benchmark/setup.py --task {task_name}"
            + (f" --schema {schema}" if schema != "native" else "")
        )
    return str(task_db)


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
    from lib.db import _db_prefix, _task_key

    task_key = _task_key(task_name)
    db_prefix = _db_prefix(task_name)
    DB_CACHE.mkdir(parents=True, exist_ok=True)
    # The cache can hold DBs for other tasks. Keep it root-private in Docker so
    # the agent cannot read another task's DB and recover a still-present target
    # table. The per-run DB copy inside workdir is the only DB the agent needs.
    try:
        DB_CACHE.chmod(0o700)
    except OSError:
        pass

    if schema == "native":
        cache_name = f"{db_prefix}_{task_key}.duckdb"
    else:
        cache_name = f"{schema}_{task_key}.duckdb"

    cached_db = DB_CACHE / cache_name

    lock = _get_db_cache_lock(cache_name)
    with lock, _db_cache_file_lock(cache_name):
        if not cached_db.exists():
            agent_db_src = Path(_resolve_agent_db(task_name, schema)).resolve()
            size_gb = agent_db_src.stat().st_size / 1e9
            print(f"  Caching database for {task_key}/{schema} ({size_gb:.1f} GB)...")
            tmp_db = cached_db.with_name(f".{cache_name}.{os.getpid()}.tmp")
            tmp_db.unlink(missing_ok=True)
            shutil.copy2(agent_db_src, tmp_db)
            try:
                tmp_db.chmod(0o600)
            except OSError:
                pass
            os.replace(tmp_db, cached_db)
            wal_src = agent_db_src.with_suffix(".duckdb.wal")
            cached_wal = cached_db.with_suffix(".duckdb.wal")
            if wal_src.exists():
                tmp_wal = cached_wal.with_name(f".{cached_wal.name}.{os.getpid()}.tmp")
                tmp_wal.unlink(missing_ok=True)
                shutil.copy2(wal_src, tmp_wal)
                try:
                    tmp_wal.chmod(0o600)
                except OSError:
                    pass
                os.replace(tmp_wal, cached_wal)
            else:
                cached_wal.unlink(missing_ok=True)
        else:
            try:
                cached_db.chmod(0o600)
                cached_db.with_suffix(".duckdb.wal").chmod(0o600)
            except OSError:
                pass

    return cached_db


def _rewrite_m4_data_sql_path(sql: str, data_root: str) -> str:
    """Point DuckDB external Parquet views at the mounted container data root."""
    root = data_root.rstrip("/")
    return M4_DATA_VIEW_PATTERN.sub(f"'{root}/", sql)


def _rewrite_external_data_views(db_path: Path) -> int:
    """Rewrite copied DuckDB views from host m4_data paths to M4BENCH_DATA_ROOT.

    Source databases store some schemas as read_parquet() views with absolute
    host paths. Docker mounts m4_data at a stable container path and this rewrites
    the per-run database copy so agents can query those views inside the
    container without exposing benchmark/tasks or ground_truth.
    """
    data_root = os.environ.get("M4BENCH_DATA_ROOT")
    if not data_root:
        return 0

    try:
        import duckdb
    except ImportError:
        return 0

    con = duckdb.connect(str(db_path))
    try:
        rows = con.execute(
            """
            SELECT sql
            FROM duckdb_views()
            WHERE NOT internal
              AND lower(sql) LIKE '%read_parquet(%m4_data/%'
            """
        ).fetchall()
        rewritten = 0
        for (sql,) in rows:
            new_sql = _rewrite_m4_data_sql_path(sql, data_root)
            if new_sql == sql:
                continue
            new_sql = new_sql.replace("CREATE VIEW ", "CREATE OR REPLACE VIEW ", 1)
            con.execute(new_sql)
            rewritten += 1
        return rewritten
    finally:
        con.close()


def setup_isolated_workdir(task_name: str, run_id: str, schema: str = "native") -> Path:
    """Create an isolated workdir in /tmp with a copy of the database.

    The database is copied (not symlinked) from the per-task cache so that
    the sandbox hook doesn't block access to it — the file lives inside the
    allowed directory.
    """
    workdir = ISOLATED_BASE / run_id
    workdir.mkdir(parents=True, exist_ok=True)

    # Copy DB from cache into workdir (same filesystem = fast)
    cached_db = _get_cached_db(task_name, schema)
    db_dest = workdir / "database.duckdb"
    if not db_dest.exists():
        print("  Copying database into workdir from cache...")
        shutil.copy2(cached_db, db_dest)
        wal_src = cached_db.with_suffix(".duckdb.wal")
        if wal_src.exists():
            shutil.copy2(wal_src, db_dest.with_suffix(".duckdb.wal"))

    rewritten = _rewrite_external_data_views(db_dest)
    if rewritten:
        print(
            f"  Rewrote {rewritten} external data views to "
            f"{os.environ['M4BENCH_DATA_ROOT']}"
        )

    # Install sandbox hook
    _create_isolated_settings(workdir)
    print(f"  Sandbox hook: {SANDBOX_HOOK} (allowed dir: {workdir})")

    return workdir


def _auth_source_root() -> Path:
    """Resolve the root directory that contains host auth state."""
    return Path(os.environ.get("M4BENCH_AUTH_ROOT", str(Path.home()))).expanduser()


def _claude_auth_source_root() -> Path:
    """Resolve the root directory that contains Claude login state."""
    return Path(
        os.environ.get("M4BENCH_CLAUDE_AUTH_ROOT", str(_auth_source_root()))
    ).expanduser()


def _copy_auth_seed(src_root: Path, relative_path: str, run_home: Path) -> bool:
    """Copy a single auth/config file into the per-run HOME if it exists."""
    src = src_root / relative_path
    if not src.exists():
        return False

    dest = run_home / relative_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dest, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dest)
    return True


def _copy_claude_login_auth(run_home: Path) -> list[str]:
    """Seed only allowlisted Claude login files into a clean per-run HOME."""
    copied: list[str] = []
    src_root = _claude_auth_source_root()
    for relative_path in CLAUDE_LOGIN_AUTH_SEEDS:
        src = src_root / relative_path
        if not src.exists():
            continue
        if not src.is_file():
            raise RuntimeError(
                f"Refusing to copy non-file Claude auth seed: {relative_path}"
            )
        dest = run_home / relative_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        copied.append(relative_path)
    return copied


def prepare_run_home(agent_name: str, run_home: Path) -> list[str]:
    """Create a clean per-run HOME seeded with minimal auth for the agent."""
    run_home.mkdir(parents=True, exist_ok=True)
    (run_home / "tmp").mkdir(exist_ok=True)

    copied: list[str] = []
    src_root = _auth_source_root()
    if agent_name == "claude":
        copied.extend(_copy_claude_login_auth(run_home))
    else:
        for relative_path in AGENT_HOME_SEEDS.get(agent_name, []):
            if _copy_auth_seed(src_root, relative_path, run_home):
                copied.append(relative_path)

    # Ensure the agent-specific directory exists even when auth is env-based.
    target_base = _skill_target_base(agent_name, run_home)
    target_base.mkdir(parents=True, exist_ok=True)

    if agent_name == "gemini":
        projects_path = run_home / ".gemini" / "projects.json"
        if not projects_path.exists():
            projects_path.write_text(json.dumps({"projects": {}}, indent=2))
        settings_path = run_home / ".gemini" / "settings.json"
        settings_path.write_text(
            json.dumps(
                {
                    "security": {
                        "auth": {"selectedType": "oauth-personal"},
                        "blockGitExtensions": True,
                    },
                    "general": {"previewFeatures": False},
                    "ide": {"enabled": False},
                    "skills": {"enabled": True},
                    "admin": {
                        "extensions": {"enabled": False},
                        "mcp": {"enabled": False},
                        "skills": {"enabled": True},
                    },
                },
                indent=2,
            )
        )
    elif agent_name == "pi-ollama":
        _configure_pi_ollama_home(run_home)
    return copied


def _configure_pi_ollama_home(run_home: Path) -> None:
    """Point Pi's copied Ollama provider config at the benchmark endpoint."""
    base_url = os.environ.get("M4BENCH_OLLAMA_BASE_URL")
    if not base_url:
        return

    models_path = run_home / ".pi" / "agent" / "models.json"
    models_path.parent.mkdir(parents=True, exist_ok=True)
    if models_path.exists():
        try:
            data = json.loads(models_path.read_text())
        except json.JSONDecodeError:
            data = {}
    else:
        data = {}

    providers = data.setdefault("providers", {})
    ollama = providers.setdefault("ollama", {})
    ollama.update(
        {
            "baseUrl": base_url,
            "api": ollama.get("api", "openai-completions"),
            "apiKey": ollama.get("apiKey", "ollama"),
        }
    )
    ollama.setdefault(
        "compat",
        {"supportsUsageInStreaming": False, "maxTokensField": "max_tokens"},
    )
    ollama.setdefault("models", [{"id": "qwen3:4b"}])
    models_path.write_text(json.dumps(data, indent=2) + "\n")


def _agent_process_env(
    agent_name: str, workdir: Path, run_home: Path
) -> dict[str, str]:
    """Build the isolated environment for an agent subprocess."""
    tmpdir = run_home / "tmp"
    tmpdir.mkdir(parents=True, exist_ok=True)

    base_passthrough_keys = {
        "PATH",
        "LANG",
        "LC_ALL",
        "SHELL",
        "TERM",
        "SSL_CERT_FILE",
        "REQUESTS_CA_BUNDLE",
        "NODE_EXTRA_CA_CERTS",
    }
    provider_keys = {
        "claude": {
            "ANTHROPIC_API_KEY",
            "M4BENCH_CLAUDE_AUTH_ROOT",
            "M4BENCH_CLAUDE_AUTH_VOLUME",
        },
        "codex": {"CODEX_API_KEY", "OPENAI_API_KEY"},
        "gemini": {"GOOGLE_API_KEY", "GEMINI_API_KEY"},
        "pi-ollama": {
            "M4BENCH_ALLOW_OLLAMA",
            "M4BENCH_OLLAMA_BASE_URL",
            "M4BENCH_OLLAMA_HOST",
            "M4BENCH_OLLAMA_PORT",
        },
    }
    passthrough_keys = base_passthrough_keys | provider_keys.get(agent_name, set())
    env = {
        key: value
        for key, value in os.environ.items()
        if key in passthrough_keys or key.startswith("LC_")
    }
    env.update(
        {
            "HOME": str(run_home),
            "TMPDIR": str(tmpdir),
            "TMP": str(tmpdir),
            "TEMP": str(tmpdir),
        }
    )
    if _agent_container_enabled():
        env.update(
            {
                "PATH": CONTAINER_PATH,
                "SHELL": "/bin/bash",
            }
        )
        for host_only_key in (
            "SSL_CERT_FILE",
            "REQUESTS_CA_BUNDLE",
            "NODE_EXTRA_CA_CERTS",
        ):
            env.pop(host_only_key, None)

    if agent_name == "codex":
        # Codex stores auth/session state under CODEX_HOME, and some Linux CLI
        # builds anchor generated shell commands at that directory's parent.
        # Keep both HOME and CODEX_HOME inside the scored workdir so relative
        # ./output.csv writes land where the harness checks. copy_results_back()
        # skips .codex, so auth/session state is not copied into result artifacts.
        codex_home = workdir / ".codex"
        codex_home.mkdir(parents=True, exist_ok=True)
        env["HOME"] = str(workdir)
        env["CODEX_HOME"] = str(codex_home)

        for relative_path in AGENT_HOME_SEEDS["codex"]:
            src = run_home / relative_path
            if src.exists():
                dest = workdir / relative_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)

    return env


def _is_database_artifact(path: Path) -> bool:
    name = path.name.lower()
    return any(name.endswith(suffix) for suffix in DATABASE_ARTIFACT_SUFFIXES)


def _should_export_result_path(path: Path) -> bool:
    """Return whether a workdir artifact is safe to export to results."""
    if path.is_symlink():
        return False
    if path.is_dir():
        return path.name not in RESULT_EXPORT_SKIP_DIRS
    if _is_database_artifact(path):
        return False
    if path.name in REQUIRED_RESULT_ARTIFACTS:
        return True
    if path.stat().st_size > RESULT_EXPORT_MAX_FILE_BYTES:
        return False
    return True


def _copy_result_item(src: Path, dest: Path) -> None:
    """Copy one artifact, recursively filtering sensitive result files."""
    if not _should_export_result_path(src):
        return
    if src.is_dir():
        dest.mkdir(parents=True, exist_ok=True)
        for child in src.iterdir():
            _copy_result_item(child, dest / child.name)
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def copy_results_back(
    workdir: Path, results_dir: Path, *, include_full_artifacts: bool = True
) -> None:
    """Copy result files from the isolated workdir to benchmark/results/.

    Skips databases, auth/provider state, symlinks, and large binary artifacts.
    Failed or contaminated runs export only result.json, so traces, stdout
    mirrors, and arbitrary agent artifacts cannot preserve leaked contents.
    """
    results_dir.mkdir(parents=True, exist_ok=True)
    if not include_full_artifacts:
        result_file = workdir / "result.json"
        if result_file.exists():
            shutil.copy2(result_file, results_dir / "result.json")
        return
    for item in workdir.iterdir():
        _copy_result_item(item, results_dir / item.name)


def _should_export_run_record(*, publishable: bool, agent_result: dict) -> bool:
    """Return whether a completed task run should appear in results discovery."""
    return publishable is True and not agent_result.get("failure_reason")


def _reset_workdir_for_retry(workdir: Path) -> None:
    """Remove stale agent outputs before another attempt in the same run."""
    preserve = {
        "database.duckdb",
        "database.duckdb.wal",
        "instruction.md",
    } | {
        Path(cfg["skill_dir"]).parts[0]
        for cfg in AGENT_COMMANDS.values()
        if cfg.get("skill_dir")
    }
    for item in workdir.iterdir():
        if item.name in preserve:
            continue
        if item.is_dir() and not item.is_symlink():
            shutil.rmtree(item, ignore_errors=True)
        else:
            item.unlink(missing_ok=True)


# ── Instruction and skill management ────────────────────────────────────────


def prepare_instruction(
    task_name: str, workdir: Path, condition: str, schema: str = "native"
) -> str:
    """Load instruction.md and fill in paths. Apply schema transforms if needed."""
    task_dir = resolve_task_dir(task_name)
    instruction = (task_dir / "instruction.md").read_text()
    isolation_note = (
        "Benchmark isolation: use only local files in the current working "
        "directory, the provided DuckDB database, and any injected skills. "
        "Do not use web search, web fetch, package installation, or external "
        "network resources.\n\n"
    )
    convention_note = (
        "Where multiple valid definitions exist (e.g., scoring thresholds, "
        "missingness handling, time-window boundaries, item-id selection), "
        "follow the standard public concept conventions for this database "
        "release. The evaluator scores agreement against a reference "
        "implementation derived from those conventions; intentional deviations "
        "will reduce reward.\n\n"
    )

    db_path = "./database.duckdb"
    output_path = "./output.csv"

    instruction = instruction.replace("{db_path}", db_path)
    instruction = instruction.replace("{output_path}", output_path)
    instruction = isolation_note + convention_note + instruction

    if schema in ("obfuscated", "restructured"):
        from lib.transform import generate_obfuscated_instruction, load_dictionary

        dictionary = load_dictionary()
        instruction = generate_obfuscated_instruction(
            instruction,
            dictionary,
            include_restructured_tables=(schema == "restructured"),
        )

    return instruction


def _skill_target_base(agent_name: str, workdir: Path) -> Path:
    """Return the agent-specific skill directory inside the workdir."""
    agent_config = AGENT_COMMANDS.get(agent_name)
    if not agent_config:
        raise ValueError(
            f"Unknown agent: {agent_name}. Available: {list(AGENT_COMMANDS)}"
        )
    return workdir / agent_config["skill_dir"]


def inject_skill(task_name: str, workdir: Path, agent_name: str) -> list[Path]:
    """Copy task-specific skill files into the agent's local skill directory.

    Using directory-level skills ensures each parallel task sees only its own
    skill(s), with no cross-contamination between concurrent runs.
    """
    task_dir = resolve_task_dir(task_name)
    skills_dir = task_dir / "skills"

    if not skills_dir.exists():
        return []

    target_base = _skill_target_base(agent_name, workdir)
    target_base.mkdir(parents=True, exist_ok=True)
    created_paths = []

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


def inject_skill_variant(
    task_name: str, workdir: Path, agent_name: str, variant: str
) -> list[Path]:
    """Inject a non-canonical skill variant from `skills-<variant>/` if present.

    Used by the with-skill-nosql and with-skill-decoy conditions. Falls back to
    the canonical skills/ directory only if the variant directory is missing
    AND the caller passes variant="" (defensive default for legacy callers).
    """
    task_dir = resolve_task_dir(task_name)
    variant_dir = task_dir / f"skills-{variant}" if variant else task_dir / "skills"

    if not variant_dir.exists():
        raise FileNotFoundError(
            f"Skill variant '{variant}' missing for task {task_name}: {variant_dir}"
        )

    target_base = _skill_target_base(agent_name, workdir)
    target_base.mkdir(parents=True, exist_ok=True)
    created_paths: list[Path] = []

    for skill_dir in variant_dir.iterdir():
        if not skill_dir.is_dir():
            continue
        target = target_base / skill_dir.name
        if target.exists():
            continue
        shutil.copytree(skill_dir, target)
        created_paths.append(target)
        print(f"  Injected skill ({variant}): {target}")

    return created_paths


def inject_all_skills(workdir: Path, agent_name: str) -> list[Path]:
    """Copy ALL benchmark skills into the agent's local skill directory."""
    all_task_dirs = list_task_dirs()
    seen_skills: set[str] = set()
    created_paths: list[Path] = []

    target_base = _skill_target_base(agent_name, workdir)
    target_base.mkdir(parents=True, exist_ok=True)

    for task_dir in all_task_dirs:
        skills_dir = task_dir / "skills"
        if not skills_dir.exists():
            continue
        for skill_dir in skills_dir.iterdir():
            if not skill_dir.is_dir() or skill_dir.name in seen_skills:
                continue
            seen_skills.add(skill_dir.name)
            target = target_base / skill_dir.name
            if not target.exists():
                shutil.copytree(skill_dir, target)
                created_paths.append(target)
                print(f"  Injected skill: {target}")

    return created_paths


# ── Agent execution ─────────────────────────────────────────────────────────


def _agent_container_image() -> str:
    return os.environ.get("M4BENCH_AGENT_CONTAINER_IMAGE", "m4bench:latest")


def _docker_bin() -> str:
    return os.environ.get("M4BENCH_DOCKER_BIN", "docker")


def _agent_container_extra_mounts() -> list[tuple[str, str]]:
    """Parse host=container mount lines provided by bench.sh."""
    mounts: list[tuple[str, str]] = []
    allowed_root = (
        Path(os.environ.get("M4BENCH_M4_DATA_DIR", BENCHMARK_ROOT.parent / "m4_data"))
        .expanduser()
        .resolve()
    )
    if allowed_root.name != "m4_data":
        raise RuntimeError(
            f"M4 data root must be a directory named m4_data: {allowed_root}"
        )
    allowed_container_prefix = "/m4_data/parquet/"
    for line in os.environ.get("M4BENCH_AGENT_CONTAINER_MOUNTS", "").splitlines():
        if not line.strip():
            continue
        if "=" not in line:
            raise RuntimeError(f"Invalid M4BENCH_AGENT_CONTAINER_MOUNTS line: {line}")
        host_path, container_path = line.split("=", 1)
        host_resolved = Path(host_path).expanduser().resolve()
        if host_resolved != allowed_root and allowed_root not in host_resolved.parents:
            raise RuntimeError(f"host mount outside M4 data root: {host_path}")
        container_parts = Path(container_path).parts
        container_resolved = Path(container_path).expanduser().resolve()
        container_is_m4_mount = container_path.startswith(allowed_container_prefix)
        container_is_host_data_mount = container_resolved == host_resolved and (
            container_resolved == allowed_root
            or allowed_root in container_resolved.parents
        )
        if not (
            (container_is_m4_mount or container_is_host_data_mount)
            and ".." not in container_parts
        ):
            raise RuntimeError(
                f"container mount outside allowed M4 data roots: {container_path}"
            )
        mounts.append((str(host_resolved), container_path))
    return mounts


def _agent_container_command(
    command: list[str],
    *,
    env: dict[str, str] | None,
    workdir: Path,
    run_home: Path | None,
) -> list[str]:
    """Build a Docker command that runs one agent command as benchagent.

    The container mounts only the agent workdir, per-run HOME, the selected
    source-data mounts, and the network-lock script. It deliberately does not
    mount benchmark/tasks, benchmark/ground_truth, benchmark/results,
    benchmark/agent_db, or dictionary.json.
    """
    network_lock = (BENCHMARK_ROOT / "network_lock.sh").resolve()
    public_env = dict(env or {})
    secret_env_file: Path | None = None
    if run_home:
        secret_env = {
            key: public_env.pop(key)
            for key in list(public_env)
            if key in SECRET_ENV_KEYS and public_env.get(key)
        }
        if secret_env:
            secret_env_file = run_home / ".m4bench" / "agent_env.sh"
            secret_env_file.parent.mkdir(parents=True, exist_ok=True)
            lines = [
                "# Generated by M4Bench. Mounted into the agent container; not passed via docker -e.",
                "set -a",
            ]
            lines.extend(
                f"{key}={shlex.quote(value)}"
                for key, value in sorted(secret_env.items())
            )
            lines.append("set +a")
            secret_env_file.write_text("\n".join(lines) + "\n")
            secret_env_file.chmod(0o600)

    docker_cmd = [
        _docker_bin(),
        "run",
        "--rm",
        "--cap-add",
        "NET_ADMIN",
        "-v",
        f"{network_lock}:/m4bench-runtime/network_lock.sh:ro",
        "-v",
        f"{workdir}:{workdir}:rw",
        "-w",
        str(workdir),
        "-e",
        f"M4BENCH_CONTAINER_WORKDIR={workdir}",
        "-e",
        f"M4BENCH_EGRESS_LOG={workdir / 'egress.jsonl'}",
    ]
    if run_home:
        docker_cmd.extend(
            [
                "-v",
                f"{run_home}:{run_home}:rw",
                "-e",
                f"M4BENCH_CONTAINER_HOME={run_home}",
            ]
        )
    if secret_env_file:
        docker_cmd.extend(["-e", f"M4BENCH_AGENT_ENV_FILE={secret_env_file}"])
    if os.environ.get("M4BENCH_ALLOW_OLLAMA") == "1":
        docker_cmd.append("--add-host=host.docker.internal:host-gateway")

    if (
        public_env
        and public_env.get("M4BENCH_CLAUDE_AUTH_ROOT")
        and public_env.get("M4BENCH_CLAUDE_AUTH_VOLUME")
    ):
        auth_root = public_env.get("M4BENCH_CLAUDE_AUTH_ROOT", "/claude-auth")
        docker_cmd.extend(
            ["-v", f"{public_env['M4BENCH_CLAUDE_AUTH_VOLUME']}:{auth_root}:rw"]
        )

    for host_path, container_path in _agent_container_extra_mounts():
        docker_cmd.extend(["-v", f"{host_path}:{container_path}:ro"])

    for key, value in public_env.items():
        docker_cmd.extend(["-e", f"{key}={value}"])

    wrapper = r"""
set -euo pipefail
bash /m4bench-runtime/network_lock.sh
export HTTPS_PROXY="http://127.0.0.1:${M4BENCH_LLM_PROXY_PORT:-18080}"
export HTTP_PROXY="$HTTPS_PROXY"
export ALL_PROXY="$HTTPS_PROXY"
export NO_PROXY="127.0.0.1,localhost"
export https_proxy="$HTTPS_PROXY"
export http_proxy="$HTTP_PROXY"
export all_proxy="$ALL_PROXY"
export no_proxy="$NO_PROXY"
if [[ -n "${M4BENCH_AGENT_ENV_FILE:-}" && -f "$M4BENCH_AGENT_ENV_FILE" ]]; then
    # shellcheck source=/dev/null
    source "$M4BENCH_AGENT_ENV_FILE"
fi
paths=("$M4BENCH_CONTAINER_WORKDIR")
if [[ -n "${M4BENCH_CONTAINER_HOME:-}" ]]; then
    paths+=("$M4BENCH_CONTAINER_HOME")
fi
if [[ -n "${M4BENCH_CLAUDE_AUTH_ROOT:-}" && -n "${M4BENCH_CONTAINER_HOME:-}" ]]; then
    auth_root="${M4BENCH_CLAUDE_AUTH_ROOT:-/claude-auth}"
    for rel in .claude.json .claude/.credentials.json .claude/credentials.json; do
        if [[ -f "$auth_root/$rel" ]]; then
            mkdir -p "$M4BENCH_CONTAINER_HOME/$(dirname "$rel")"
            cp "$auth_root/$rel" "$M4BENCH_CONTAINER_HOME/$rel"
        fi
    done
    chmod -R go-rwx "$auth_root" 2>/dev/null || true
fi
for path in "${paths[@]}"; do
    mkdir -p "$path"
    chown -R benchagent:benchagent "$path" 2>/dev/null || true
done
set +e
runuser -u benchagent -m -- bash -lc 'cd "$M4BENCH_CONTAINER_WORKDIR"; exec "$@"' bash "$@"
status=$?
if [[ -n "${M4BENCH_CLAUDE_AUTH_ROOT:-}" && -n "${M4BENCH_CONTAINER_HOME:-}" ]]; then
    auth_root="${M4BENCH_CLAUDE_AUTH_ROOT:-/claude-auth}"
    for rel in .claude.json .claude/.credentials.json .claude/credentials.json; do
        if [[ -f "$M4BENCH_CONTAINER_HOME/$rel" ]]; then
            mkdir -p "$auth_root/$(dirname "$rel")"
            cp "$M4BENCH_CONTAINER_HOME/$rel" "$auth_root/$rel"
        fi
    done
fi
chmod -R a+rwX "${paths[@]}" 2>/dev/null || true
exit "$status"
"""
    docker_cmd.extend([_agent_container_image(), "bash", "-lc", wrapper, "bash"])
    docker_cmd.extend(command)
    return docker_cmd


def _run_agent_container_process(
    command: list[str],
    *,
    env: dict[str, str] | None,
    workdir: Path,
    run_home: Path | None,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
) -> subprocess.Popen[str]:
    return subprocess.Popen(
        _agent_container_command(
            command,
            env=env,
            workdir=workdir,
            run_home=run_home,
        ),
        stdin=subprocess.DEVNULL,
        stdout=stdout,
        stderr=stderr,
        text=True,
        cwd=str(workdir),
        start_new_session=True,
    )


def _run_agent_container_check(
    command: list[str],
    *,
    env: dict[str, str] | None,
    workdir: Path,
    run_home: Path | None,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        _agent_container_command(
            command,
            env=env,
            workdir=workdir,
            run_home=run_home,
        ),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        cwd=str(workdir),
        timeout=timeout,
        check=False,
    )


def run_agent(
    instruction: str,
    agent_name: str,
    workdir: Path,
    model: str | None = None,
    verbose: bool = False,
    isolated: bool = False,
    run_home: Path | None = None,
    reasoning_effort: str | None = BENCHMARK_REASONING_EFFORT,
) -> dict:
    """Invoke an agent CLI with the instruction. Returns result dict."""
    agent_config = AGENT_COMMANDS.get(agent_name)
    if not agent_config:
        raise ValueError(
            f"Unknown agent: {agent_name}. Available: {list(AGENT_COMMANDS)}"
        )

    cmd = list(agent_config["cmd"])

    if model:
        if agent_name == "claude":
            cmd.extend(["--model", model])
        elif agent_name == "codex":
            cmd.extend(["-m", model])
        elif agent_name == "gemini":
            if cmd and cmd[-1] == "-p":
                cmd = cmd[:-1]
                cmd.extend(["-m", model, "-p"])
            else:
                cmd.extend(["-m", model])
        elif agent_name == "pi-ollama":
            if cmd and cmd[-1] == "-p":
                cmd = cmd[:-1]
                cmd.extend(["--model", model, "-p"])
            else:
                cmd.extend(["--model", model])

    resolved_reasoning_effort = _resolve_reasoning_effort(agent_name, reasoning_effort)
    cmd.extend(_reasoning_args_for_agent(agent_name, resolved_reasoning_effort))

    agent_container = isolated and _agent_container_enabled()
    if agent_container and agent_name == "codex":
        # The outer Docker container is the isolation boundary in release-grade
        # runs. Codex's inner bwrap sandbox cannot create user namespaces inside
        # that container on common Docker Desktop setups.
        cmd.extend(["-c", 'sandbox_mode="danger-full-access"'])

    if isolated and agent_name == "claude":
        cmd.extend(["--disallowedTools", NETWORK_DENY_TOOLS])

    # Capture structured trace for agent CLIs that support JSONL output.
    trace_path = workdir / "trace.jsonl"
    use_json_trace = bool(agent_config.get("json_trace"))
    if agent_name == "claude" and use_json_trace:
        cmd.extend(["--output-format", "stream-json", "--verbose"])
    elif agent_name == "codex" and use_json_trace:
        cmd.extend(["--json", "-C", str(workdir)])

    cmd.append(instruction)

    env = None
    if run_home:
        env = _agent_process_env(agent_name, workdir, run_home)

    # Run agent as benchagent when isolated (user-level filesystem + network isolation).
    agent_creds = _resolve_agent_creds() if isolated and not agent_container else None
    if agent_creds:
        uid, gid = agent_creds
        _chown_recursive(workdir, uid, gid)
        if run_home:
            _chown_recursive(run_home, uid, gid)
        print(f"  Agent user: {AGENT_USER} (uid={uid})")
    elif agent_container:
        print(f"  Agent container: {_agent_container_image()} ({AGENT_USER})")

    print(f"  Running {agent_name}{'  (verbose)' if verbose else ''}...")
    start = time.time()

    def _kill_process_group(process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        except OSError:
            process.kill()
            return
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                return
            except OSError:
                process.kill()

    try:
        if agent_container:
            process = _run_agent_container_process(
                cmd,
                env=env,
                workdir=workdir,
                run_home=run_home,
            )
        else:
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(workdir),
                env=env,
                user=agent_creds[0] if agent_creds else None,
                group=agent_creds[1] if agent_creds else None,
                start_new_session=True,
            )
        output_lines = []

        def _drain_stdout() -> None:
            with open(trace_path, "w") as trace_file:
                if process.stdout is None:
                    return
                for line in process.stdout:
                    if use_json_trace:
                        trace_file.write(line)
                        if verbose:
                            _print_trace_line(line, agent_name)
                    else:
                        trace_file.write(line)
                        if verbose:
                            print(f"  │ {line}", end="")
                    output_lines.append(line)

        reader = threading.Thread(target=_drain_stdout, daemon=True)
        reader.start()
        process.wait(timeout=1800)
        reader.join(timeout=5)
        elapsed = time.time() - start
        full_output = "".join(output_lines)
        return {
            "returncode": process.returncode,
            "stdout": full_output[-10000:],
            "stderr": "",
            "elapsed_seconds": round(elapsed, 1),
            "trace_file": str(trace_path),
            "reasoning_effort": resolved_reasoning_effort,
        }
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        if "process" in locals():
            _kill_process_group(process)
            reader.join(timeout=5)
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": "TIMEOUT after 30 minutes",
            "elapsed_seconds": round(elapsed, 1),
            "trace_file": str(trace_path),
            "failure_reason": "timeout",
            "reasoning_effort": (
                resolved_reasoning_effort
                if "resolved_reasoning_effort" in locals()
                else PROVIDER_DEFAULT_REASONING
            ),
        }
    except Exception as exc:
        elapsed = time.time() - start
        if "process" in locals():
            _kill_process_group(process)
            if "reader" in locals():
                reader.join(timeout=5)
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": str(exc),
            "elapsed_seconds": round(elapsed, 1),
            "trace_file": str(trace_path),
            "failure_reason": "exception",
            "reasoning_effort": (
                resolved_reasoning_effort
                if "resolved_reasoning_effort" in locals()
                else PROVIDER_DEFAULT_REASONING
            ),
        }


def _print_trace_line(line: str, agent_name: str) -> None:
    """Print a human-readable summary of a structured trace line.

    Claude and Codex emit different JSONL schemas. We extract what we can and
    fall back to printing the raw line.
    """
    line = line.rstrip()
    if not line:
        return

    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        print(f"  │ {line}")
        return

    if agent_name == "codex":
        _print_codex_trace_line(event, line)
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


def _print_codex_trace_line(event: dict, raw_line: str) -> None:
    """Print a compact summary for Codex JSONL events."""
    etype = event.get("type", "")
    item = event.get("item", {})
    item_type = item.get("type", "")

    if etype == "item.started" and item_type == "command_execution":
        print(f"  │ [cmd] {item.get('command', '')[:120]}")
        return

    if etype == "item.completed":
        if item_type == "agent_message":
            text = item.get("text", "")
            for text_line in text.splitlines():
                if text_line.strip():
                    print(f"  │ {text_line}")
            return

        if item_type == "command_execution":
            exit_code = item.get("exit_code")
            if exit_code not in (None, 0):
                print(f"  │ [cmd failed:{exit_code}] {item.get('command', '')[:100]}")
            return

    if etype == "turn.completed":
        usage = event.get("usage", {})
        if usage:
            print(
                "  │ "
                f"[usage] in={usage.get('input_tokens', 0)} "
                f"out={usage.get('output_tokens', 0)}"
            )
            return

    if etype not in {"thread.started", "turn.started"}:
        print(f"  │ {raw_line}")


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
        return _filter_by_mode(matched, args.mode)

    if args.task == "all":
        tasks = [load_task_config(td)["metadata"]["name"] for td in list_task_dirs()]
        return _filter_by_mode(tasks, args.mode)

    return [args.task]


def _filter_by_mode(task_names: list[str], mode: str | None) -> list[str]:
    """Filter tasks by mode (standard/raw) if specified."""
    if not mode:
        return task_names
    filtered = []
    for name in task_names:
        task_dir = resolve_task_dir(name)
        config = load_task_config(task_dir)
        if config["metadata"].get("mode") == mode:
            filtered.append(name)
    if not filtered:
        print(f"Error: No tasks match --mode '{mode}'")
        sys.exit(1)
    return filtered


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
    results_root: Path | None = None,
    max_retries: int = 0,
    retry_delay_seconds: int = 15,
    wait_on_claude_rate_limit: bool = False,
    reasoning_effort: str | None = BENCHMARK_REASONING_EFFORT,
) -> dict:
    """Run a single benchmark task end-to-end. Returns the full result dict."""
    results_root = (results_root or RESULTS_DIR).resolve()
    ensure_results_manifest(results_root)

    # Verify prerequisites
    try:
        resolve_task_dir(task_name)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return {"task": task_name, "test_results": {"reward": 0.0}, "error": str(e)}

    try:
        agent_db_path = _resolve_agent_db(task_name, schema)
    except FileNotFoundError as exc:
        msg = str(exc)
        print(f"Error: {msg}")
        return {
            "task": task_name,
            "schema": schema,
            "test_results": {"reward": 0.0},
            "agent_result": {"failure_reason": "missing_agent_db"},
            "error": msg,
        }
    agent_db = _agent_db_metadata(agent_db_path)

    resolved_reasoning_effort = _resolve_reasoning_effort(agent_name, reasoning_effort)

    # Create working directory
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    schema_tag = f"_{schema}" if schema != "native" else ""
    run_id = f"{task_name}_{condition}{schema_tag}_{agent_name}_{model or 'default'}_t{trial}_{timestamp}"

    if isolated:
        workdir = setup_isolated_workdir(task_name, run_id, schema)
        final_results_dir = results_root / run_id
    else:
        workdir = results_root / run_id
        workdir.mkdir(parents=True, exist_ok=True)
        final_results_dir = None

    publishable, publishable_reason = _publishable_environment(isolated, agent_name)

    print(f"\n{'=' * 60}")
    print(f"M4Bench: {task_name}")
    print(
        f"Condition: {condition} | Schema: {schema} | Agent: {agent_name} | Model: {model or 'default'}"
    )
    print(
        f"Reasoning: {resolved_reasoning_effort}"
        f" (requested: {reasoning_effort or BENCHMARK_REASONING_EFFORT})"
    )
    if isolated:
        has_agent_user = _resolve_agent_creds() is not None
        print(
            f"Isolation: ON (sandboxed workdir, per-run HOME"
            f"{', user=' + AGENT_USER if has_agent_user else ''}"
            f", network=API-only)"
        )
    else:
        print("WARNING: Isolation OFF - results are NOT suitable for release")
    if not publishable:
        print(f"Release eligibility: NO ({publishable_reason})")
    else:
        print(f"Release eligibility: YES ({publishable_reason})")
    print(f"Working dir: {workdir}")
    print(f"Results root: {results_root}")
    print(f"{'=' * 60}\n")

    # Set up workdir with data
    if not isolated:
        setup_workdir(task_name, workdir, schema)

    export_full_artifacts = False
    export_result_record = False
    run_home = None
    use_run_home = isolated or agent_name == "claude"

    if use_run_home:
        run_home = ISOLATED_BASE / f"{run_id}_home" if isolated else workdir / "_home"
        seeded = prepare_run_home(agent_name, run_home)
        seed_msg = ", ".join(seeded) if seeded else "env-only auth"
        print(f"  Per-run HOME isolation: ON ({seed_msg})")

    if isolated and _agent_visible_results_root(results_root, workdir, run_home):
        raise RuntimeError(
            f"Refusing publishable run: results root is agent-visible: {results_root}"
        )

    # Inject skills into the agent's workdir-local skill directory.
    # Each task's workdir is unique, so parallel runs never interfere.
    try:
        if condition == "with-skill":
            print("Injecting task skill into workdir...")
            inject_skill(task_name, workdir, agent_name)
        elif condition == "with-skill-all":
            print("Injecting all benchmark skills into workdir...")
            inject_all_skills(workdir, agent_name)
        elif condition == "with-skill-nosql":
            print("Injecting NO-SQL skill variant into workdir...")
            inject_skill_variant(task_name, workdir, agent_name, variant="nosql")
        elif condition == "with-skill-decoy":
            print("Injecting DECOY skill variant into workdir...")
            inject_skill_variant(task_name, workdir, agent_name, variant="decoy")
        elif condition == "with-skill-rawsql":
            print("Injecting RAW-SQL skill variant (matched-content) into workdir...")
            inject_skill_variant(task_name, workdir, agent_name, variant="rawsql")

        instruction = prepare_instruction(task_name, workdir, condition, schema)
        (workdir / "instruction.md").write_text(instruction)

        filesystem_canary = run_filesystem_canary(
            agent_name,
            workdir,
            run_home,
            isolated=isolated,
            enforce=isolated
            and (_running_in_container() or _agent_container_enabled()),
        )
        if filesystem_canary["passed"]:
            print("  Filesystem canary: PASS")
        elif filesystem_canary["required"]:
            print(
                "  Filesystem canary: FAIL ("
                + ", ".join(filesystem_canary["failures"])
                + ")"
            )
        else:
            print(
                "  Filesystem canary: WARN ("
                + ", ".join(filesystem_canary["failures"])
                + ")"
            )

        attempts = max_retries + 1
        agent_result = {}
        claude_memory_validation: dict | None = None
        if not filesystem_canary["passed"] and filesystem_canary["required"]:
            agent_result = {
                "returncode": -1,
                "stdout": "",
                "stderr": "Filesystem canary failed",
                "elapsed_seconds": 0,
                "trace_file": "",
                "failure_reason": "filesystem_canary",
                "filesystem_canary": filesystem_canary,
            }
        else:
            for attempt in range(1, attempts + 1):
                if attempt > 1:
                    print(f"  Retry {attempt - 1}/{max_retries}...")
                    _reset_workdir_for_retry(workdir)

                agent_result = run_agent(
                    instruction,
                    agent_name,
                    workdir,
                    model,
                    reasoning_effort=reasoning_effort,
                    verbose=verbose,
                    isolated=isolated,
                    run_home=run_home,
                )
                print(
                    f"  Agent finished in {agent_result['elapsed_seconds']}s "
                    f"(exit code: {agent_result['returncode']})"
                )

                external_tools = _detect_external_tool_use(
                    agent_result.get("trace_file", "")
                )
                disallowed_egress = _detect_disallowed_egress(workdir)
                if disallowed_egress:
                    agent_result["failure_reason"] = "disallowed_egress"
                    agent_result["egress_violations"] = disallowed_egress
                    print(
                        "  Disallowed network egress detected: "
                        + ", ".join(disallowed_egress[:5])
                    )
                    break
                if external_tools:
                    agent_result["failure_reason"] = "external_tool_use"
                    agent_result["external_tools"] = external_tools
                    print(
                        "  Disallowed external tool use detected: "
                        + ", ".join(external_tools)
                    )
                    break

                if agent_name == "claude":
                    claude_memory_validation = _validate_claude_memory_paths(
                        agent_result.get("trace_file", ""), run_home
                    )
                    if claude_memory_validation["violations"]:
                        agent_result["failure_reason"] = "claude_memory_escape"
                        agent_result["claude_memory_validation"] = (
                            claude_memory_validation
                        )
                        print(
                            "  Claude memory path escaped per-run HOME: "
                            + ", ".join(claude_memory_validation["violations"])
                        )
                        break

                failure_reason = _detect_agent_failure_reason(agent_name, agent_result)
                if not failure_reason or attempt >= attempts:
                    if failure_reason:
                        agent_result["failure_reason"] = failure_reason
                    break

                if failure_reason == "auth":
                    agent_result["failure_reason"] = failure_reason
                    print(
                        "  Claude auth failed; run 'claude login' in the benchmark runtime and retry."
                    )
                    break

                if failure_reason == "rate_limit":
                    wait_seconds = retry_delay_seconds
                    if wait_on_claude_rate_limit:
                        reset_at = _extract_claude_rate_limit_reset_at(
                            agent_result.get("trace_file", "")
                        )
                        if reset_at:
                            wait_seconds = max(reset_at - int(time.time()), 0)
                        print(
                            "  Claude five-hour limit hit; "
                            f"waiting {wait_seconds}s before retry..."
                        )
                    else:
                        print(
                            "  Claude rate limit detected; "
                            f"waiting {wait_seconds}s before retry..."
                        )
                    time.sleep(wait_seconds)
                    continue

        if (
            agent_result
            and not agent_result.get("failure_reason")
            and agent_result.get("returncode") not in (0, None)
        ):
            agent_result["failure_reason"] = "agent_nonzero_exit"

        # Check if output was produced
        output_file = workdir / "output.csv"
        contamination_lint = {
            "passed": True,
            "violations": [],
            "patterns": list(SENSITIVE_CONTENT_PATTERNS),
        }
        if agent_result.get("failure_reason"):
            pass
        else:
            contamination_lint = lint_run_contamination(
                workdir,
                task_name,
                run_id=run_id,
                prior_run_ids=_collect_prior_run_ids(results_root, run_id),
            )
            if contamination_lint["passed"]:
                print("  Contamination lint: PASS")
            else:
                print(
                    "  Contamination lint: FAIL ("
                    + "; ".join(contamination_lint["violations"][:5])
                    + ")"
                )
                agent_result["failure_reason"] = "contamination_lint"
                agent_result["contamination_lint"] = contamination_lint

        if agent_result.get("failure_reason") == "filesystem_canary":
            test_results = {
                "passed": 0,
                "failed": 0,
                "errors": 1,
                "total": 1,
                "reward": 0.0,
                "pytest_output": "Filesystem canary failed",
                "pytest_stderr": "",
            }
        elif agent_result.get("failure_reason") == "external_tool_use":
            test_results = {
                "passed": 0,
                "failed": 0,
                "errors": 1,
                "total": 1,
                "reward": 0.0,
                "pytest_output": (
                    "Disallowed external tool use: "
                    + ", ".join(agent_result.get("external_tools", []))
                ),
                "pytest_stderr": "",
            }
        elif agent_result.get("failure_reason") == "disallowed_egress":
            test_results = {
                "passed": 0,
                "failed": 0,
                "errors": 1,
                "total": 1,
                "reward": 0.0,
                "pytest_output": (
                    "Disallowed network egress: "
                    + ", ".join(agent_result.get("egress_violations", []))
                ),
                "pytest_stderr": "",
            }
        elif agent_result.get("failure_reason") == "claude_memory_escape":
            test_results = {
                "passed": 0,
                "failed": 0,
                "errors": 1,
                "total": 1,
                "reward": 0.0,
                "pytest_output": (
                    "Claude memory path escaped per-run HOME: "
                    + ", ".join(
                        agent_result.get("claude_memory_validation", {}).get(
                            "violations", []
                        )
                    )
                ),
                "pytest_stderr": "",
            }
        elif agent_result.get("failure_reason") == "contamination_lint":
            test_results = {
                "passed": 0,
                "failed": 0,
                "errors": 1,
                "total": 1,
                "reward": 0.0,
                "pytest_output": (
                    "Contamination lint failed: "
                    + "; ".join(contamination_lint["violations"])
                ),
                "pytest_stderr": "",
            }
        elif agent_result.get("failure_reason"):
            reason = agent_result["failure_reason"]
            test_results = {
                "passed": 0,
                "failed": 0,
                "errors": 1,
                "total": 1,
                "reward": 0.0,
                "pytest_output": f"Agent run failed: {reason}",
                "pytest_stderr": str(agent_result.get("stderr", "")),
            }
        elif not output_file.exists():
            print(f"\nNo output file produced at {output_file}")
            agent_result["failure_reason"] = "no_output"
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

        # Decouple artifact retention from strict diagnostic pass. We keep
        # output.csv + trace.jsonl whenever the run is contamination-clean and
        # the agent did not trip an explicit failure reason. This preserves
        # partial-correct attempts for audit while still redacting traces from
        # contaminated/failure runs (sanitize_agent_result_for_storage handles
        # the stricter stdout/stderr redaction below via export_full_artifacts).
        export_full_artifacts = contamination_lint.get(
            "passed"
        ) is True and not agent_result.get("failure_reason")

        token_usage = aggregate_token_usage(
            agent_name, agent_result.get("trace_file", "")
        )

        # Save full result
        full_result = {
            "task": task_name,
            "condition": condition,
            "schema": schema,
            "agent": agent_name,
            "model": model,
            "reasoning_effort": reasoning_effort or BENCHMARK_REASONING_EFFORT,
            "resolved_reasoning_effort": resolved_reasoning_effort,
            "trial": trial,
            "isolated": isolated,
            "publishable": publishable,
            "publishable_reason": publishable_reason,
            "timestamp": timestamp,
            "run_id": run_id,
            "container_name": os.environ.get("M4BENCH_CONTAINER_NAME"),
            "results_root": str(results_root),
            "agent_db": agent_db,
            "agent_result": sanitize_agent_result_for_storage(
                agent_result, safe_run=export_full_artifacts
            ),
            "test_results": sanitize_test_results_for_storage(test_results),
            "filesystem_canary": filesystem_canary,
            "contamination_lint": contamination_lint,
            "token_usage": token_usage,
        }
        if agent_name == "claude":
            claude_memory_validation = claude_memory_validation or (
                _validate_claude_memory_paths(
                    agent_result.get("trace_file", ""), run_home
                )
                if agent_result
                else {
                    "validated": False,
                    "paths": [],
                    "violations": [],
                    "reason": "Claude agent did not run",
                }
            )
            full_result.update(
                {
                    "claude_auth_method": (
                        "api-key"
                        if os.environ.get("ANTHROPIC_API_KEY")
                        else "claude-login"
                    ),
                    "claude_home_ephemeral": run_home is not None,
                    "claude_memory_validated_ephemeral": claude_memory_validation[
                        "validated"
                    ],
                    "claude_memory_validation": claude_memory_validation,
                }
            )
        result_file = workdir / "result.json"
        with open(result_file, "w") as f:
            json.dump(full_result, f, indent=2, default=str)
        export_result_record = _should_export_run_record(
            publishable=publishable,
            agent_result=agent_result,
        )
        print(f"\nFull result saved to: {result_file}")

        # Report trace location
        trace_file = workdir / "trace.jsonl"
        if trace_file.exists():
            trace_size = trace_file.stat().st_size / 1024
            print(f"Agent trace: {trace_file} ({trace_size:.0f} KB)")

        return full_result

    finally:
        # Skills live in the workdir's agent-specific control directory and are
        # cleaned up with the workdir. No host-level cleanup needed.
        if isolated and run_home and run_home.exists():
            shutil.rmtree(run_home, ignore_errors=True)
        if final_results_dir and export_result_record:
            print(f"\nCopying results to {final_results_dir}...")
            copy_results_back(
                workdir,
                final_results_dir,
                include_full_artifacts=export_full_artifacts,
            )
            print(f"Results available at: {final_results_dir}")
        elif final_results_dir:
            print(
                "\nSkipping results export for non-publishable or failed run: "
                f"{final_results_dir}"
            )
        if isolated and workdir.exists():
            shutil.rmtree(workdir, ignore_errors=True)


def run_leak_canary(
    agent_name: str,
    model: str | None,
    verbose: bool,
    isolated: bool,
    results_root: Path | None = None,
    reasoning_effort: str | None = BENCHMARK_REASONING_EFFORT,
) -> dict:
    """Run an adversarial isolation canary with the real agent CLI."""
    results_root = (results_root or RESULTS_DIR).resolve()
    ensure_results_manifest(results_root)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_id = f"leak-canary_{agent_name}_{model or 'default'}_{timestamp}"

    if isolated:
        workdir = ISOLATED_BASE / run_id
        workdir.mkdir(parents=True, exist_ok=True)
        _create_isolated_settings(workdir)
        final_results_dir = results_root / run_id
    else:
        workdir = results_root / run_id
        workdir.mkdir(parents=True, exist_ok=True)
        final_results_dir = None

    run_home = None
    publishable, publishable_reason = _publishable_environment(isolated, agent_name)
    try:
        if isolated:
            run_home = ISOLATED_BASE / f"{run_id}_home"
            prepare_run_home(agent_name, run_home)

        if isolated and _agent_visible_results_root(results_root, workdir, run_home):
            raise RuntimeError(
                f"Refusing leak canary: results root is agent-visible: {results_root}"
            )

        path_list = "\n".join(f"- {path}" for path in LEAK_CANARY_PATHS)
        instruction = f"""Isolation access check.

Verify that benchmark-private paths are not available from this runtime. For
each listed path, perform a simple existence/readability probe such as
`test -e`, `test -r`, or `ls`. Do not attempt to bypass permissions or search
unlisted locations.

{path_list}

Write canary_report.json in the current directory. Use exactly this JSON shape:
{{"leak_found": true|false, "probed_paths": ["exact path", "..."], "evidence": ["short path or reason", "..."]}}.
Set leak_found=true only if you actually read sensitive file contents or listed
a sensitive directory. Failed permission checks are not leaks. Include every
path you attempted in probed_paths using the exact path strings above.
"""
        (workdir / "instruction.md").write_text(instruction)

        filesystem_canary = run_filesystem_canary(
            agent_name,
            workdir,
            run_home,
            isolated=isolated,
            enforce=isolated
            and (_running_in_container() or _agent_container_enabled()),
        )
        agent_result: dict
        if not filesystem_canary["passed"] and filesystem_canary["required"]:
            agent_result = {
                "returncode": -1,
                "stdout": "",
                "stderr": "Filesystem canary failed",
                "elapsed_seconds": 0,
                "trace_file": "",
                "failure_reason": "filesystem_canary",
            }
        else:
            agent_result = run_agent(
                instruction,
                agent_name,
                workdir,
                model,
                reasoning_effort=reasoning_effort,
                verbose=verbose,
                isolated=isolated,
                run_home=run_home,
            )

        report_path = workdir / "canary_report.json"
        report = {}
        if report_path.exists():
            try:
                report = json.loads(report_path.read_text())
            except json.JSONDecodeError as exc:
                report = {"parse_error": str(exc)}

        leak_found = bool(report.get("leak_found"))
        canary_validation = validate_leak_canary_report(report)
        passed = (
            filesystem_canary["passed"]
            and agent_result.get("returncode") == 0
            and report_path.exists()
            and canary_validation["passed"]
            and not leak_found
        )

        full_result = {
            "task": "leak-canary",
            "condition": "adversarial",
            "agent": agent_name,
            "model": model,
            "reasoning_effort": reasoning_effort or BENCHMARK_REASONING_EFFORT,
            "resolved_reasoning_effort": _resolve_reasoning_effort(
                agent_name, reasoning_effort
            ),
            "trial": 0,
            "isolated": isolated,
            "publishable": publishable,
            "publishable_reason": publishable_reason,
            "timestamp": timestamp,
            "run_id": run_id,
            "results_root": str(results_root),
            "agent_result": agent_result,
            "filesystem_canary": filesystem_canary,
            "canary_report": report,
            "canary_validation": canary_validation,
            "canary_passed": passed,
            "test_results": {
                "passed": 1 if passed else 0,
                "failed": 0 if passed else 1,
                "errors": 0,
                "total": 1,
                "reward": 1.0 if passed else 0.0,
                "pytest_output": "Leak canary passed"
                if passed
                else "Leak canary failed",
                "pytest_stderr": "",
            },
        }
        (workdir / "result.json").write_text(json.dumps(full_result, indent=2))

        print(f"Leak canary: {'PASS' if passed else 'FAIL'}")
        if report:
            print(f"Report: {report}")
        if canary_validation["missing_paths"]:
            print(
                "Missing probe evidence for: "
                + ", ".join(canary_validation["missing_paths"])
            )
        return full_result
    finally:
        if isolated and run_home and run_home.exists():
            shutil.rmtree(run_home, ignore_errors=True)
        if final_results_dir:
            copy_results_back(workdir, final_results_dir)
            print(f"Results available at: {final_results_dir}")
        if isolated and workdir.exists():
            shutil.rmtree(workdir, ignore_errors=True)


# ── Thread safety ──────────────────────────────────────────────────────────

_db_cache_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
_db_cache_locks_guard = threading.Lock()


def _get_db_cache_lock(cache_name: str) -> threading.Lock:
    """Get a per-cache-name lock for thread-safe DB caching."""
    with _db_cache_locks_guard:
        return _db_cache_locks[cache_name]


@contextlib.contextmanager
def _db_cache_file_lock(cache_name: str):
    """Serialize DB cache creation across parallel matrix processes."""
    DB_CACHE.mkdir(parents=True, exist_ok=True)
    lock_path = DB_CACHE / f"{cache_name}.lock"
    with lock_path.open("a+") as handle:
        try:
            lock_path.chmod(0o600)
        except OSError:
            pass
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


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
    results_root: Path,
    max_retries: int = 0,
    retry_delay_seconds: int = 15,
    wait_on_claude_rate_limit: bool = False,
    reasoning_effort: str | None = BENCHMARK_REASONING_EFFORT,
) -> list[dict]:
    """Execute runs in parallel using ThreadPoolExecutor.

    Skills are injected into each task's workdir-local control directory, so
    parallel runs never interfere — no locking or batch pre-injection needed.
    """
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
                results_root,
                max_retries,
                retry_delay_seconds,
                wait_on_claude_rate_limit,
                reasoning_effort=reasoning_effort,
            )
        except Exception as e:
            result = {
                "task": task_name,
                "trial": trial,
                "condition": condition,
                "test_results": {"reward": 0.0},
                "error": str(e),
            }

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


def _trial_numbers(start_trial: int, seeds: int) -> list[int]:
    """Return the trial ids that should be executed for this campaign."""
    return list(range(start_trial, start_trial + seeds))


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
    task_group.add_argument(
        "--leak-canary",
        action="store_true",
        help="Run an adversarial isolation canary instead of a benchmark task",
    )
    parser.add_argument(
        "--condition",
        choices=[
            "no-skill",
            "with-skill",
            "with-skill-all",
            "with-skill-nosql",
            "with-skill-decoy",
            "with-skill-rawsql",
        ],
        help="Evaluation condition",
    )
    parser.add_argument("--agent", choices=list(AGENT_COMMANDS), help="Agent to use")
    parser.add_argument(
        "--model",
        help="Model override (e.g., opus, sonnet, gpt-5.5, gemini-3.1-pro-preview)",
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
    parser.add_argument("--trial", type=int, default=1, help="Trial number")
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Stream agent output in real time",
    )
    parser.add_argument(
        "--no-isolation",
        action="store_true",
        help="Disable isolation (local debugging ONLY — results are NOT publishable)",
    )
    # Keep --isolated for backward compat — it's now the default and a no-op.
    parser.add_argument("--isolated", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--schema",
        choices=["native", "obfuscated", "restructured"],
        default="native",
        help="Database schema condition for contamination analysis (default: native)",
    )
    parser.add_argument(
        "--mode",
        choices=["standard", "raw"],
        default=None,
        help="Filter tasks by mode (e.g., --mode raw for contamination runs)",
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
    parser.add_argument(
        "--results-root",
        help="Directory for run outputs; use a fresh root for release-grade campaigns",
    )
    parser.add_argument(
        "--delay-between-runs-seconds",
        type=int,
        default=0,
        help="Sleep between sequential runs (useful for subscription-backed pacing)",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=0,
        help="Retry failed agent runs this many times",
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

    # Isolation is the default; --no-isolation must be explicit.
    isolated = not args.no_isolation
    results_root = resolve_results_root(args.results_root)
    ensure_results_manifest(results_root)
    if not isolated:
        print(
            "\n*** WARNING: Isolation disabled (--no-isolation). ***\n"
            "*** Results from this run are NOT suitable for release. ***\n"
        )

    if args.list:
        resolve_tasks(args)
        return

    if not args.agent:
        parser.error("--agent is required when running tasks or leak canary")
    try:
        resolved_reasoning_effort = _resolve_reasoning_effort(
            args.agent, args.reasoning_effort
        )
    except ValueError as e:
        parser.error(str(e))

    if args.leak_canary:
        run_leak_canary(
            args.agent,
            args.model,
            args.verbose,
            isolated,
            results_root,
            reasoning_effort=args.reasoning_effort,
        )
        return

    task_names = resolve_tasks(args)

    # --condition is required when actually running tasks
    if not args.condition:
        parser.error("--condition is required when running tasks")

    if args.parallel > 4:
        print(
            f"Warning: --parallel {args.parallel} exceeds recommended max of 4 on 18GB RAM"
        )
    if args.agent == "claude" and args.parallel > 1:
        print(
            "Warning: Claude subscription runs are much more reliable with --parallel 1."
        )
    if args.delay_between_runs_seconds and args.parallel > 1:
        print(
            "Warning: --delay-between-runs-seconds applies only to sequential execution."
        )

    # Build run matrix: (task_name, trial) for all tasks x seeds.
    raw_matrix = [
        (task_name, trial)
        for trial in _trial_numbers(args.trial, args.seeds)
        for task_name in task_names
    ]
    if args.parallel > 1 and len(task_names) > 1:
        # Sort so consecutive entries come from different families (parent dir)
        def _family(task_name: str) -> str:
            try:
                return resolve_task_dir(task_name).parent.name
            except FileNotFoundError:
                return task_name

        from itertools import zip_longest

        by_family: dict[str, list] = defaultdict(list)
        for item in raw_matrix:
            by_family[_family(item[0])].append(item)
        # Round-robin across families
        family_lists = list(by_family.values())
        run_matrix = [
            item
            for batch in zip_longest(*family_lists)
            for item in batch
            if item is not None
        ]
    else:
        run_matrix = raw_matrix

    print(
        f"\nRun matrix: {len(run_matrix)} runs ({len(task_names)} tasks x {args.seeds} seeds)"
    )
    print(f"Results root: {results_root}")
    print(
        f"Reasoning: {resolved_reasoning_effort} (requested: {args.reasoning_effort})"
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
                isolated,
                args.schema,
                results_root,
                args.max_retries,
                args.retry_delay_seconds,
                args.wait_on_claude_rate_limit,
                reasoning_effort=args.reasoning_effort,
            )
            results.append(result)
            if args.delay_between_runs_seconds > 0 and len(results) < len(run_matrix):
                print(f"Sleeping {args.delay_between_runs_seconds}s before next run...")
                time.sleep(args.delay_between_runs_seconds)
    else:
        # Parallel execution
        results = _run_parallel(
            run_matrix,
            args.condition,
            args.agent,
            args.model,
            args.verbose,
            isolated,
            args.schema,
            args.parallel,
            results_root,
            args.max_retries,
            args.retry_delay_seconds,
            args.wait_on_claude_rate_limit,
            reasoning_effort=args.reasoning_effort,
        )

    # Print summary
    if len(results) > 1:
        _print_summary(results, args.seeds)

    # Save batch result JSON
    if len(results) > 1:
        batch_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        batch_path = results_root / f"batch_{batch_ts}.json"
        batch_data = {
            "condition": args.condition,
            "agent": args.agent,
            "model": args.model,
            "reasoning_effort": args.reasoning_effort,
            "resolved_reasoning_effort": resolved_reasoning_effort,
            "schema": args.schema,
            "parallel": args.parallel,
            "seeds": args.seeds,
            "results_root": str(results_root),
            "results": results,
        }
        with open(batch_path, "w") as f:
            json.dump(batch_data, f, indent=2, default=str)
        print(f"\nBatch results saved to: {batch_path}")


if __name__ == "__main__":
    main()
