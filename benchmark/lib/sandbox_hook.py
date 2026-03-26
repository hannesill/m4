#!/usr/bin/env python3
"""PreToolUse hook that restricts agent file access to an allowed directory.

Receives JSON on stdin from Claude CLI with tool_name and tool_input.
Exit codes: 0 = allow, 2 = block.

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
import sys


def resolve_path(path: str, workdir: str) -> str:
    """Resolve a path to its real absolute form."""
    if not os.path.isabs(path):
        path = os.path.join(workdir, path)
    return os.path.realpath(path)


def is_allowed(path: str, allowed_dir: str) -> bool:
    """Check if a resolved path is within the allowed directory."""
    resolved = resolve_path(path, allowed_dir)
    # Resolve the allowed dir too (e.g., /tmp -> /private/tmp on macOS)
    real_allowed = os.path.realpath(allowed_dir)
    return resolved == real_allowed or resolved.startswith(real_allowed + os.sep)


def extract_paths_from_command(command: str) -> list[str]:
    """Extract file paths from a shell command (best-effort).

    Catches:
    - Absolute paths: /foo/bar
    - Relative paths with directory components: ../foo, ./bar
    - Home expansion: ~/foo
    """
    paths = []
    # Absolute paths
    paths.extend(re.findall(r'(?<![a-zA-Z0-9_=])(/[^\s;&|><\'"(){}$`]+)', command))
    # Relative paths with ../ or ./
    paths.extend(re.findall(r'(?<![a-zA-Z0-9_=])(\.\.?/[^\s;&|><\'"(){}$`]*)', command))
    # Home directory expansion
    paths.extend(re.findall(r'(?<![a-zA-Z0-9_=])(~/[^\s;&|><\'"(){}$`]*)', command))
    return paths


def main():
    if len(sys.argv) < 2:
        print("Usage: sandbox_hook.py <allowed_dir>", file=sys.stderr)
        sys.exit(1)

    allowed_dir = os.path.realpath(sys.argv[1])

    try:
        data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)  # Can't parse = allow (fail open for non-tool events)

    tool = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

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
        for path in extract_paths_from_command(command):
            # Expand ~ to home dir
            expanded = os.path.expanduser(path)
            if not is_allowed(expanded, allowed_dir):
                print(
                    f"SANDBOX: blocked Bash command referencing {path}",
                    file=sys.stderr,
                )
                sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
