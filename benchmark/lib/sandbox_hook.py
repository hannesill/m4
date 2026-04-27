#!/usr/bin/env python3
"""PreToolUse hook that restricts agent file access to an allowed directory.

Receives JSON on stdin from Claude CLI with tool_name and tool_input.
Exit codes: 0 = allow, 2 = block.

This is defence-in-depth.  The primary filesystem barrier is user-based
isolation (the agent subprocess runs as benchagent, which cannot read
root-owned directories like ground_truth/).  This hook adds a second
layer specifically for Claude, catching accidental path references before
the OS-level check even fires.

Usage (in .claude/settings.json):
    {
        "hooks": {
            "PreToolUse": [{
                "matcher": "Read|Write|Edit|Glob|Grep|Bash",
                "hooks": [{"type": "command", "command": "python3 /path/to/sandbox_hook.py /allowed/dir"}]
            }]
        }
    }
"""

import json
import os
import re
import shlex
import sys

# Substrings that must never appear in any tool input — these reference
# benchmark internals that the agent should not access.
BLOCKED_SUBSTRINGS = [
    "/benchmark/ground_truth",
    "/benchmark/evaluate",
    "/benchmark/lib/compare",
    "/benchmark/lib/test_task",
    "/benchmark/lib/ground_truth",
    "/benchmark/agent_db",
    "/benchmark/tasks",
    "/benchmark/results",
    "/benchmark/lib/dictionary.json",
    "/tmp/clinskillsbench/_db_cache",
    "/host-auth",
    "/claude-auth",
    "ground_truth/",
    "ground_truth.csv",
    "ground_truth.sql",
    "dictionary.json",
]


def resolve_path(path: str, workdir: str) -> str:
    """Resolve a path to its real absolute form."""
    if not os.path.isabs(path):
        path = os.path.join(workdir, path)
    return os.path.realpath(path)


def is_allowed(path: str, allowed_dir: str, workdir: str | None = None) -> bool:
    """Check if a resolved path is within the allowed directory."""
    resolved = resolve_path(path, workdir or allowed_dir)
    # Resolve the allowed dir too (e.g., /tmp -> /private/tmp on macOS)
    real_allowed = os.path.realpath(allowed_dir)
    return resolved == real_allowed or resolved.startswith(real_allowed + os.sep)


def extract_paths_from_command(command: str) -> list[str]:
    """Extract file paths from a shell command (best-effort).

    Catches:
    - Absolute paths: /foo/bar
    - Relative paths with directory components: ../foo, ./bar
    - Home expansion: ~/foo
    - Paths inside quotes: "/foo/bar", '/foo/bar'
    """
    paths = []
    # Absolute paths (including inside single/double quotes)
    paths.extend(re.findall(r"""(/[^\s;&|><(){}$`]+)""", command))
    # Quoted absolute paths
    paths.extend(re.findall(r"""['"](/[^'"]+)['"]""", command))
    # Relative paths with ../ or ./
    paths.extend(re.findall(r'(?<![a-zA-Z0-9_=])(\.\.?/[^\s;&|><\'"(){}$`]*)', command))
    # Home directory expansion
    paths.extend(re.findall(r'(?<![a-zA-Z0-9_=])(~/[^\s;&|><\'"(){}$`]*)', command))
    try:
        for token in shlex.split(command):
            if token.startswith(("/", "./", "../", "~/")):
                paths.append(token)
    except ValueError:
        pass
    return paths


def _check_blocked_substrings(raw_input: str) -> str | None:
    """Return the first blocked substring found in raw_input, or None."""
    lower = raw_input.lower()
    for pattern in BLOCKED_SUBSTRINGS:
        if pattern.lower() in lower:
            return pattern
    return None


def main():
    if len(sys.argv) < 2:
        print("Usage: sandbox_hook.py <allowed_dir>", file=sys.stderr)
        sys.exit(1)

    allowed_dir = os.path.realpath(sys.argv[1])

    try:
        data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        print("SANDBOX: blocked malformed hook payload", file=sys.stderr)
        sys.exit(2)

    tool = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    # ── Blocked-substring check (all tools) ──────────────────────────
    # Serialise the full tool input and scan for sensitive path fragments.
    raw = json.dumps(tool_input)
    hit = _check_blocked_substrings(raw)
    if hit:
        print(f"SANDBOX: blocked — input references '{hit}'", file=sys.stderr)
        sys.exit(2)

    # ── Per-tool path checks ─────────────────────────────────────────

    # Tools with explicit file_path
    if tool in ("Read", "Write", "Edit"):
        path = tool_input.get("file_path", "")
        if path and not is_allowed(path, allowed_dir):
            print(f"SANDBOX: blocked {tool} access to {path}", file=sys.stderr)
            sys.exit(2)

    # Tools with path parameter
    elif tool in ("Glob", "Grep"):
        path = tool_input.get("path", "")
        if path and not is_allowed(path, allowed_dir):
            print(f"SANDBOX: blocked {tool} access to {path}", file=sys.stderr)
            sys.exit(2)

    # Bash: extract and check all paths in the command
    elif tool == "Bash":
        command = tool_input.get("command", "")
        cwd = tool_input.get("cwd") or allowed_dir
        for path in extract_paths_from_command(command):
            # Expand ~ to home dir
            expanded = os.path.expanduser(path)
            if not is_allowed(expanded, allowed_dir, cwd):
                print(
                    f"SANDBOX: blocked Bash command referencing {path}",
                    file=sys.stderr,
                )
                sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
