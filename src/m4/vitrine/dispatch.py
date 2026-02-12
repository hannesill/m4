"""Dispatch: spawn headless Claude Code agents for study operations.

The agent lives inside a single vitrine card. It has read-only access to study
files and cards (provided in the prompt context), evaluates correctness and
reproducibility, and streams its analysis output into the card progressively.

Flow:
    1. Server creates a markdown card immediately (visible to the user)
    2. Spawns ``claude -p`` with study context + skill instructions in the prompt
    3. Monitor reads stdout line-by-line, updating the card content via WebSocket
    4. On completion/failure, the card is finalized with a status badge
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from m4.vitrine.server import DisplayServer
    from m4.vitrine.study_manager import StudyManager

logger = logging.getLogger(__name__)

_SKILLS_DIR = Path(__file__).parent.parent / "skills" / "system"
_DISPATCH_TIMEOUT = 1800  # 30 minutes
_UPDATE_INTERVAL = 0.5  # seconds between card updates (debounce)
_SANDBOX_SUFFIX = "_reproduce"  # suffix for sandboxed output directory copies

# task name -> (skill directory, card title, allowed tools)
_TASK_CONFIG = {
    "reproduce": ("reproduce-study", "Reproducibility Audit", "Bash,Read,Glob,Grep"),
    "report": ("export-report", "Study Report", "Read,Glob,Grep"),
}


@dataclass
class DispatchInfo:
    """Metadata for a running dispatch."""

    task: str
    study: str
    card_id: str = ""
    process: subprocess.Popen | None = None
    monitor_task: asyncio.Task | None = None
    pid: int | None = None
    status: str = "running"
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def build_prompt(
    task: str,
    study: str,
    study_manager: StudyManager,
    work_dir: Path | None = None,
) -> str:
    """Build a prompt for the dispatched agent.

    Includes skill instructions and study context. Points the agent at the
    study's output directory so it can use Read/Glob/Grep to explore files.

    Args:
        task: Dispatch task name (e.g. "reproduce", "report").
        study: Study label.
        study_manager: Active study manager.
        work_dir: If given, the agent is pointed at this directory instead of
            the original output directory. Used for sandboxed reproduce runs.
    """
    config = _TASK_CONFIG.get(task)
    if config is None:
        raise ValueError(
            f"Unknown dispatch task: {task!r} (expected one of {list(_TASK_CONFIG)})"
        )

    skill_dir_name, _, _ = config
    skill_path = _SKILLS_DIR / skill_dir_name / "SKILL.md"
    if not skill_path.exists():
        raise ValueError(f"Skill file not found: {skill_path}")

    skill_content = skill_path.read_text()

    # Study context (card summaries, decisions, annotations)
    study_manager.refresh()
    ctx = study_manager.build_context(study)
    ctx_json = json.dumps(ctx, indent=2, default=str)

    # Output directory path for the agent to explore
    if work_dir is not None:
        output_dir_str = str(work_dir)
    else:
        output_dir = study_manager.get_output_dir(study)
        output_dir_str = (
            str(output_dir) if output_dir and output_dir.exists() else "(none)"
        )

    sandbox_note = ""
    if work_dir is not None:
        sandbox_note = (
            "\n> **Sandbox:** This is a copy of the original study output. "
            "You may freely run scripts and modify files here — the original "
            "study data is untouched.\n"
        )

    return f"""{skill_content}

---

## Dispatch Context

**Study:** {study}
**Output directory:** `{output_dir_str}`
{sandbox_note}
Use Glob, Read, and Grep to explore the output directory. Key locations:
- `scripts/` — analysis scripts (numbered .py files)
- `data/` — saved DataFrames (.parquet)
- `plots/` — figures (.png, .html)
- `PROTOCOL.md` — research protocol
- `STUDY.md` — study description
- `RESULTS.md` — findings (if completed)

### Study Context (cards, decisions, annotations)

```json
{ctx_json}
```

---

## Output Instructions

Your output is streamed directly into a single vitrine card as markdown.
Write your analysis as markdown to stdout — that IS the card content.
Do NOT use any vitrine API calls or `show()`.
Structure your output with clear headings. Start writing immediately so the
user sees progress.
"""


def _find_claude() -> str | None:
    """Find the ``claude`` CLI binary in PATH."""
    return shutil.which("claude")


async def _create_progress_card(
    card_id: str,
    title: str,
    study: str,
    server: DisplayServer,
) -> None:
    """Create an initial progress card and broadcast it."""
    from m4.vitrine._types import CardDescriptor, CardType
    from m4.vitrine.artifacts import _serialize_card

    card = CardDescriptor(
        card_id=card_id,
        card_type=CardType.MARKDOWN,
        title=title,
        study=study,
        timestamp=datetime.now(timezone.utc).isoformat(),
        preview={"text": "*Agent starting...*"},
    )

    # Persist in the study's artifact store
    if server.study_manager:
        _, store = server.study_manager.get_or_create_study(study)
        if store:
            store.store_card(card)
            server.study_manager.register_card(
                card_id, server.study_manager._label_to_dir.get(study, "")
            )

    # Broadcast to browser
    await server._broadcast({"type": "display.add", "card": _serialize_card(card)})


async def _update_card_content(
    card_id: str,
    text: str,
    study: str,
    server: DisplayServer,
    title: str | None = None,
) -> None:
    """Update a card's markdown content and broadcast the change."""
    from m4.vitrine._types import CardType

    # Update in store
    if server.study_manager:
        _, store = server.study_manager.get_or_create_study(study)
        if store:
            store.update_card(card_id, preview={"text": text})

    # Broadcast update (minimal payload)
    card_data = {
        "card_id": card_id,
        "card_type": CardType.MARKDOWN.value,
        "title": title,
        "study": study,
        "preview": {"text": text},
    }
    await server._broadcast(
        {"type": "display.update", "card_id": card_id, "card": card_data}
    )


def _create_sandbox(output_dir: Path) -> Path:
    """Copy the study output directory into a sibling sandbox for safe execution.

    Returns the path to the sandbox copy. The sandbox is named
    ``<original_name>_reproduce`` and is placed next to the original.
    """
    sandbox = output_dir.parent / (output_dir.name + _SANDBOX_SUFFIX)
    if sandbox.exists():
        shutil.rmtree(sandbox)
    shutil.copytree(output_dir, sandbox)
    logger.info(f"Created sandbox copy: {sandbox}")
    return sandbox


def _cleanup_sandbox(sandbox: Path) -> None:
    """Remove a sandbox directory if it exists."""
    if sandbox.exists():
        shutil.rmtree(sandbox, ignore_errors=True)
        logger.info(f"Cleaned up sandbox: {sandbox}")


async def dispatch(
    task: str,
    study: str,
    server: DisplayServer,
) -> DispatchInfo:
    """Spawn a headless agent that streams its output into a single card.

    Creates an immediate progress card, spawns ``claude -p`` with read-only
    tools, and monitors stdout to update the card progressively.

    For the ``reproduce`` task, the study's output directory is copied into a
    sandbox so the agent can freely run scripts without modifying originals.
    """
    if not server.study_manager:
        raise ValueError("No study manager available")

    # Check for existing dispatch
    existing = server._dispatches.get(study)
    if existing and existing.status == "running":
        raise RuntimeError(f"Dispatch already running for study '{study}'")

    claude_path = _find_claude()
    if claude_path is None:
        raise ValueError(
            "claude CLI not found in PATH. Install Claude Code: "
            "https://docs.anthropic.com/en/docs/claude-code"
        )

    config = _TASK_CONFIG.get(task)
    if config is None:
        raise ValueError(f"Unknown task: {task!r}")
    _, card_title, allowed_tools = config

    # For reproduce tasks, sandbox the output directory
    work_dir: Path | None = None
    if task == "reproduce":
        output_dir = server.study_manager.get_output_dir(study)
        if output_dir and output_dir.exists():
            work_dir = _create_sandbox(output_dir)

    # Create the progress card immediately
    card_id = uuid.uuid4().hex[:12]
    await _create_progress_card(card_id, card_title, study, server)

    prompt = build_prompt(task, study, server.study_manager, work_dir=work_dir)

    # Spawn headless agent; stream-json for progressive card updates
    proc = subprocess.Popen(
        [
            claude_path,
            "-p",
            "-",
            "--output-format",
            "stream-json",
            "--verbose",
            "--dangerously-skip-permissions",
            "--allowedTools",
            allowed_tools,
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )

    # Feed prompt and close stdin
    if proc.stdin:
        proc.stdin.write(prompt.encode())
        proc.stdin.close()

    info = DispatchInfo(
        task=task,
        study=study,
        card_id=card_id,
        process=proc,
        pid=proc.pid,
        status="running",
        extra={"sandbox": str(work_dir)} if work_dir else {},
    )
    server._dispatches[study] = info

    # Broadcast started event
    await server._broadcast(
        {
            "type": "agent.started",
            "study": study,
            "task": task,
            "pid": proc.pid,
        }
    )

    # Start the streaming monitor
    info.monitor_task = asyncio.create_task(_stream_monitor(info, server))

    logger.info(f"Dispatched '{task}' for '{study}' (pid={proc.pid}, card={card_id})")
    return info


def _parse_stream_event(line: str) -> tuple[str, str]:
    """Parse a stream-json line and return (event_kind, display_text).

    event_kind is one of: "text", "tool_use", "tool_result", "error",
    "result", "ignore".
    display_text is the content to show for that event (may be empty).
    """
    try:
        obj = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return ("ignore", "")

    evt_type = obj.get("type", "")

    if evt_type == "assistant":
        # Agent message — may contain text blocks and/or tool_use blocks
        msg = obj.get("message", {})
        parts: list[str] = []
        kind = "text"
        for block in msg.get("content", []):
            bt = block.get("type", "")
            if bt == "text":
                parts.append(block.get("text", ""))
            elif bt == "tool_use":
                kind = "tool_use"
                name = block.get("name", "?")
                inp = block.get("input", {})
                # Short summary of what the tool is doing
                if name == "Read":
                    path = inp.get("file_path", "")
                    parts.append(f"\n\n> *Reading `{Path(path).name}`...*\n\n")
                elif name == "Glob":
                    parts.append(
                        f"\n\n> *Searching for `{inp.get('pattern', '?')}`...*\n\n"
                    )
                elif name == "Grep":
                    parts.append(
                        f'\n\n> *Searching for "{inp.get("pattern", "?")}"...*\n\n'
                    )
                elif name == "Bash":
                    cmd = inp.get("command", "")
                    short = cmd[:80] + ("..." if len(cmd) > 80 else "")
                    parts.append(f"\n\n> *Running `{short}`...*\n\n")
                else:
                    parts.append(f"\n\n> *Using {name}...*\n\n")
        return (kind, "".join(parts))

    if evt_type == "result":
        # Final result — contains the complete text in "result"
        return ("result", obj.get("result", ""))

    return ("ignore", "")


async def _stream_monitor(info: DispatchInfo, server: DisplayServer) -> None:
    """Parse stream-json events from the agent and update the card."""
    proc = info.process
    if proc is None or proc.stdout is None:
        return

    loop = asyncio.get_event_loop()
    accumulated = ""
    final_result: str | None = None
    last_update = 0.0
    config = _TASK_CONFIG.get(info.task, ("", "", ""))
    _, card_title, _ = config

    try:

        def _read_line() -> bytes:
            return proc.stdout.readline()

        while True:
            line_bytes = await asyncio.wait_for(
                loop.run_in_executor(None, _read_line),
                timeout=_DISPATCH_TIMEOUT,
            )

            if not line_bytes:
                break

            line = line_bytes.decode(errors="replace").strip()
            if not line:
                continue

            kind, text = _parse_stream_event(line)

            if kind == "result":
                # The result event has the clean final text
                final_result = text
                continue

            if kind == "ignore" or not text:
                continue

            accumulated += text

            # Update card (debounced)
            now = loop.time()
            if now - last_update >= _UPDATE_INTERVAL:
                await _update_card_content(
                    info.card_id, accumulated, info.study, server, card_title
                )
                last_update = now

        # Wait for process exit
        returncode = await loop.run_in_executor(None, proc.wait)

        if returncode == 0:
            info.status = "completed"
            # Prefer final_result (clean text without tool-use indicators)
            display = final_result or accumulated
            if not display.strip():
                display = "*Agent completed with no output.*"
            await _update_card_content(
                info.card_id, display, info.study, server, card_title
            )
            await server._broadcast(
                {
                    "type": "agent.completed",
                    "study": info.study,
                    "task": info.task,
                }
            )
        else:
            info.status = "failed"
            stderr = ""
            if proc.stderr:
                try:
                    stderr = proc.stderr.read().decode(errors="replace")[:2000]
                except Exception:
                    pass
            info.error = stderr or f"Process exited with code {returncode}"
            error_text = accumulated + f"\n\n---\n**Error:** {info.error}"
            await _update_card_content(
                info.card_id, error_text, info.study, server, card_title
            )
            await server._broadcast(
                {
                    "type": "agent.failed",
                    "study": info.study,
                    "task": info.task,
                    "error": info.error,
                }
            )

    except asyncio.TimeoutError:
        try:
            proc.terminate()
            await asyncio.sleep(2)
            if proc.poll() is None:
                proc.kill()
        except OSError:
            pass
        info.status = "failed"
        info.error = f"Timed out after {_DISPATCH_TIMEOUT}s"
        timeout_text = (
            accumulated + f"\n\n---\n**Timed out** after {_DISPATCH_TIMEOUT}s"
        )
        await _update_card_content(
            info.card_id, timeout_text, info.study, server, card_title
        )
        await server._broadcast(
            {
                "type": "agent.failed",
                "study": info.study,
                "task": info.task,
                "error": info.error,
            }
        )

    except Exception as e:
        info.status = "failed"
        info.error = str(e)
        logger.exception(f"Monitor error for dispatch '{info.task}'")

    finally:
        # Clean up sandbox copy if one was created
        sandbox = info.extra.get("sandbox")
        if sandbox:
            _cleanup_sandbox(Path(sandbox))


async def cancel(study: str, server: DisplayServer) -> bool:
    """Cancel a running dispatch for a study."""
    info = server._dispatches.get(study)
    if info is None or info.status != "running":
        return False

    proc = info.process
    if proc is not None:
        try:
            proc.terminate()
        except OSError:
            pass

    if info.monitor_task is not None:
        info.monitor_task.cancel()

    info.status = "cancelled"

    # Clean up sandbox copy if one was created
    sandbox = info.extra.get("sandbox")
    if sandbox:
        _cleanup_sandbox(Path(sandbox))

    # Update card with cancellation notice
    await _update_card_content(
        info.card_id,
        "*Cancelled by user.*",
        info.study,
        server,
        _TASK_CONFIG.get(info.task, ("", ""))[1],
    )

    await server._broadcast(
        {
            "type": "agent.failed",
            "study": study,
            "task": info.task,
            "error": "Cancelled by user",
        }
    )
    return True


def cleanup_dispatches(server: DisplayServer) -> None:
    """Terminate all running dispatches. Called on server shutdown."""
    for study, info in server._dispatches.items():
        if info.status == "running" and info.process is not None:
            try:
                info.process.terminate()
            except OSError:
                pass
            info.status = "cancelled"
        # Clean up any sandbox copies
        sandbox = info.extra.get("sandbox")
        if sandbox:
            _cleanup_sandbox(Path(sandbox))
    server._dispatches.clear()
