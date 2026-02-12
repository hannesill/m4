"""Dispatch: spawn headless Claude Code agents for study operations.

The agent lives inside a dedicated AGENT card. The researcher sees a config
form first, can tune parameters (model, budget, instructions), then
explicitly runs the agent. Output streams inline (collapsible), and
completed cards auto-collapse to a compact summary row.

Flow:
    1. ``create_agent_card()`` creates an AGENT card with config preview
    2. Researcher reviews/tweaks config in the browser
    3. ``run_agent()`` spawns ``claude -p`` and streams output into the card
    4. On completion/failure, the card is finalized with status + duration

Up to ``_MAX_CONCURRENT`` agents can run simultaneously.
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
_MAX_CONCURRENT = 5  # global running agent limit
_MODEL_CONTEXT_WINDOWS = {
    "sonnet": 200_000,
    "opus": 200_000,
    "haiku": 200_000,
}

# task name -> (skill directory, card title, allowed tools)
_TASK_CONFIG = {
    "reproduce": ("reproduce-study", "Reproducibility Audit", "Bash,Read,Glob,Grep"),
    "report": ("export-report", "Study Report", "Read,Glob,Grep"),
    "paper": ("draft-paper", "Paper Draft", "Bash,Read,Glob,Grep,Write"),
}


@dataclass
class DispatchInfo:
    """Metadata for an agent dispatch (pending, running, or completed)."""

    task: str
    study: str
    card_id: str = ""
    # Config (set at creation, user can override before run)
    model: str = "sonnet"
    budget: float | None = None
    additional_prompt: str = ""
    # Runtime
    process: subprocess.Popen | None = None
    monitor_task: asyncio.Task | None = None
    pid: int | None = None
    status: str = "pending"  # pending -> running -> completed/failed/cancelled
    error: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    accumulated_output: str = ""  # live output buffer for cancel recovery
    last_activity_at: str | None = None  # ISO — last output line received
    extra: dict[str, Any] = field(default_factory=dict)


def build_prompt(
    task: str,
    study: str,
    study_manager: StudyManager,
    work_dir: Path | None = None,
    additional_prompt: str = "",
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
        additional_prompt: Extra instructions from the researcher.
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

    additional_section = ""
    if additional_prompt.strip():
        additional_section = (
            f"\n### Additional Instructions\n\n{additional_prompt.strip()}\n"
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
{additional_section}
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


def _build_agent_preview(
    task: str,
    status: str,
    model: str = "sonnet",
    additional_prompt: str = "",
    budget: float | None = None,
) -> dict[str, Any]:
    """Build the preview dict for an agent card."""
    config = _TASK_CONFIG.get(task, ("", "", ""))
    _, _, allowed_tools = config

    # Build full prompt preview
    skill_dir_name = _TASK_CONFIG.get(task, ("", "", ""))[0]
    skill_path = _SKILLS_DIR / skill_dir_name / "SKILL.md"
    full_prompt = ""
    if skill_path.exists():
        full_prompt = skill_path.read_text()

    return {
        "task": task,
        "status": status,
        "model": model,
        "tools": allowed_tools.split(",") if allowed_tools else [],
        "prompt_preview": full_prompt[:200] + ("..." if len(full_prompt) > 200 else ""),
        "full_prompt": full_prompt,
        "additional_prompt": additional_prompt,
        "budget": budget,
        "output": "",
        "started_at": None,
        "completed_at": None,
        "duration": None,
        "error": None,
        "last_activity_at": None,
        "usage": {
            "input_tokens": 0,
            "output_tokens": 0,
            "context_window": _MODEL_CONTEXT_WINDOWS.get(model, 200_000),
            "cost_usd": None,
        },
    }


async def create_agent_card(
    task: str,
    study: str,
    server: DisplayServer,
) -> DispatchInfo:
    """Create an AGENT card with config preview. Does not start the agent.

    The card appears in the browser with a config form. The researcher
    can adjust model, budget, and instructions before clicking "Run Agent".
    """
    from m4.vitrine._types import CardDescriptor, CardType
    from m4.vitrine.artifacts import _serialize_card

    if not server.study_manager:
        raise ValueError("No study manager available")

    config = _TASK_CONFIG.get(task)
    if config is None:
        raise ValueError(f"Unknown task: {task!r}")
    _, card_title, _ = config

    card_id = uuid.uuid4().hex[:12]
    preview = _build_agent_preview(task, "pending")

    card = CardDescriptor(
        card_id=card_id,
        card_type=CardType.AGENT,
        title=card_title,
        study=study,
        timestamp=datetime.now(timezone.utc).isoformat(),
        preview=preview,
    )

    # Persist in the study's artifact store
    _, store = server.study_manager.get_or_create_study(study)
    if store:
        store.store_card(card)
        server.study_manager.register_card(
            card_id, server.study_manager._label_to_dir.get(study, "")
        )

    # Broadcast to browser
    await server._broadcast({"type": "display.add", "card": _serialize_card(card)})

    info = DispatchInfo(
        task=task,
        study=study,
        card_id=card_id,
        status="pending",
    )
    server._dispatches[card_id] = info

    logger.info(f"Created agent card '{task}' for '{study}' (card={card_id})")
    return info


async def _update_agent_card(
    card_id: str,
    study: str,
    server: DisplayServer,
    preview_updates: dict[str, Any],
    title: str | None = None,
) -> None:
    """Update an agent card's preview and broadcast the change."""
    from m4.vitrine._types import CardType

    # Merge updates into existing preview in store, then broadcast full card
    full_preview = dict(preview_updates)
    stored_title = title
    if server.study_manager:
        _, store = server.study_manager.get_or_create_study(study)
        if store:
            cards = store.list_cards()
            for c in cards:
                if c.card_id == card_id:
                    new_preview = dict(c.preview)
                    new_preview.update(preview_updates)
                    store.update_card(card_id, preview=new_preview)
                    full_preview = new_preview
                    if stored_title is None:
                        stored_title = c.title
                    break

    # Build broadcast payload with full card data (not partial)
    card_data: dict[str, Any] = {
        "card_id": card_id,
        "card_type": CardType.AGENT.value,
        "study": study,
        "preview": full_preview,
    }
    if stored_title is not None:
        card_data["title"] = stored_title

    await server._broadcast(
        {"type": "display.update", "card_id": card_id, "card": card_data}
    )


async def run_agent(
    card_id: str,
    server: DisplayServer,
    config: dict[str, Any] | None = None,
) -> DispatchInfo:
    """Start the agent for an existing AGENT card.

    Validates the global concurrency limit, applies config overrides,
    spawns the process, and starts the output monitor.

    Args:
        card_id: ID of the AGENT card to run.
        server: The DisplayServer instance.
        config: Optional overrides (model, budget, additional_prompt).
    """
    if not server.study_manager:
        raise ValueError("No study manager available")

    info = server._dispatches.get(card_id)
    if info is None:
        raise ValueError(f"No agent card found: {card_id}")
    if info.status != "pending":
        raise RuntimeError(
            f"Agent card {card_id} is not pending (status={info.status})"
        )

    # Check global concurrency limit
    running = sum(1 for d in server._dispatches.values() if d.status == "running")
    if running >= _MAX_CONCURRENT:
        raise RuntimeError(f"Maximum {_MAX_CONCURRENT} concurrent agents reached")

    claude_path = _find_claude()
    if claude_path is None:
        raise ValueError(
            "claude CLI not found in PATH. Install Claude Code: "
            "https://docs.anthropic.com/en/docs/claude-code"
        )

    # Apply config overrides
    if config:
        if "model" in config:
            info.model = config["model"]
        if "budget" in config:
            info.budget = config["budget"]
        if "additional_prompt" in config:
            info.additional_prompt = config["additional_prompt"]

    task_config = _TASK_CONFIG.get(info.task)
    if task_config is None:
        raise ValueError(f"Unknown task: {info.task!r}")
    _, card_title, allowed_tools = task_config

    # For reproduce tasks, sandbox the output directory
    work_dir: Path | None = None
    if info.task == "reproduce":
        output_dir = server.study_manager.get_output_dir(info.study)
        if output_dir and output_dir.exists():
            work_dir = _create_sandbox(output_dir)
            info.extra["sandbox"] = str(work_dir)
    elif info.task == "paper":
        output_dir = server.study_manager.get_output_dir(info.study)
        if output_dir and output_dir.exists():
            paper_dir, copied = _create_paper_workspace(output_dir)
            work_dir = paper_dir
            info.extra["paper_workspace"] = str(paper_dir)
            info.extra["paper_copies"] = copied

    prompt = build_prompt(
        info.task,
        info.study,
        server.study_manager,
        work_dir=work_dir,
        additional_prompt=info.additional_prompt,
    )

    # Build CLI args
    cli_args = [
        claude_path,
        "-p",
        "-",
        "--output-format",
        "stream-json",
        "--verbose",
        "--dangerously-skip-permissions",
        "--allowedTools",
        allowed_tools,
    ]
    if info.model and info.model != "sonnet":
        cli_args.extend(["--model", info.model])
    if info.budget is not None:
        cli_args.extend(["--max-turns", str(int(info.budget))])

    # Spawn headless agent
    proc = subprocess.Popen(
        cli_args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

    # Feed prompt and close stdin
    if proc.stdin:
        proc.stdin.write(prompt.encode())
        proc.stdin.close()

    info.process = proc
    info.pid = proc.pid
    info.status = "running"
    info.started_at = datetime.now(timezone.utc).isoformat()

    # Update card preview to running
    await _update_agent_card(
        card_id,
        info.study,
        server,
        {
            "status": "running",
            "model": info.model,
            "additional_prompt": info.additional_prompt,
            "budget": info.budget,
            "started_at": info.started_at,
            "last_activity_at": info.started_at,
            "output": "*Agent starting...*",
            "usage": {
                "input_tokens": 0,
                "output_tokens": 0,
                "context_window": _MODEL_CONTEXT_WINDOWS.get(info.model, 200_000),
                "cost_usd": None,
            },
        },
        title=card_title,
    )

    # Broadcast started event (for toast)
    await server._broadcast(
        {
            "type": "agent.started",
            "study": info.study,
            "task": info.task,
            "card_id": card_id,
            "pid": proc.pid,
        }
    )

    # Start the streaming monitor
    info.monitor_task = asyncio.create_task(_stream_monitor(info, server))

    logger.info(
        f"Dispatched '{info.task}' for '{info.study}' (pid={proc.pid}, card={card_id})"
    )
    return info


def _parse_stream_event(line: str) -> tuple[str, str, dict[str, Any] | None]:
    """Parse a stream-json line and return (event_kind, display_text, usage).

    event_kind is one of: "text", "tool_use", "tool_result", "error",
    "result", "ignore".
    display_text is the content to show for that event (may be empty).
    usage is a dict with token/cost info if available, else None.
    """
    try:
        obj = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return ("ignore", "", None)

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

        # Extract usage from assistant message
        usage_data = None
        raw_usage = msg.get("usage")
        if raw_usage:
            usage_data = {
                "input_tokens": raw_usage.get("input_tokens", 0),
                "output_tokens": raw_usage.get("output_tokens", 0),
                "cache_read": raw_usage.get("cache_read_input_tokens", 0),
                "cache_creation": raw_usage.get("cache_creation_input_tokens", 0),
            }
        return (kind, "".join(parts), usage_data)

    if evt_type == "result":
        # Extract final usage from result event
        usage_data: dict[str, Any] | None = None
        model_usage = obj.get("modelUsage", {})
        if model_usage:
            for _model_name, mu in model_usage.items():
                usage_data = {
                    "input_tokens": mu.get("inputTokens", 0),
                    "output_tokens": mu.get("outputTokens", 0),
                    "cache_read": mu.get("cacheReadInputTokens", 0),
                    "cache_creation": mu.get("cacheCreationInputTokens", 0),
                    "context_window": mu.get("contextWindow"),
                    "cost_usd": mu.get("costUSD"),
                }
                break
        elif obj.get("total_cost_usd") is not None:
            usage_data = {"cost_usd": obj["total_cost_usd"]}
        return ("result", obj.get("result", ""), usage_data)

    return ("ignore", "", None)


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


def _create_paper_workspace(output_dir: Path) -> tuple[Path, list[str]]:
    """Create a paper workspace with copies of study artifacts.

    The agent works entirely inside ``paper/`` — it reads from the copies
    and writes new files alongside them.  Original study files are never
    touched.

    Returns:
        Tuple of (paper_dir, list of copied item names).
    """
    paper_dir = output_dir / "paper"
    paper_dir.mkdir(exist_ok=True)
    copied: list[str] = []
    for item in ("scripts", "data", "plots", "PROTOCOL.md", "RESULTS.md", "REPORT.md"):
        src = output_dir / item
        dst = paper_dir / item
        if src.is_dir() and not dst.exists():
            shutil.copytree(src, dst)
            copied.append(item)
        elif src.is_file() and not dst.exists():
            shutil.copy2(src, dst)
            copied.append(item)
    logger.info(f"Created paper workspace: {paper_dir} (copied: {copied})")
    return paper_dir, copied


def _cleanup_paper_workspace(paper_dir: Path, copied_items: list[str]) -> None:
    """Remove copied study files from the paper workspace.

    Leaves only agent-generated files (paper.md, abstract.md, figures/,
    references.bib, build.sh, README.md, etc.).
    """
    for item in copied_items:
        path = paper_dir / item
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.is_file():
            path.unlink(missing_ok=True)
    logger.info(f"Cleaned up paper workspace copies: {paper_dir}")


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

    # Usage tracking — input_tokens is latest turn (context fill),
    # output_tokens is accumulated across turns
    usage: dict[str, Any] = {
        "input_tokens": 0,
        "output_tokens": 0,
        "context_window": _MODEL_CONTEXT_WINDOWS.get(info.model, 200_000),
        "cost_usd": None,
    }

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

            kind, text, event_usage = _parse_stream_event(line)

            if kind == "result":
                # The result event has the clean final text
                final_result = text
                # Capture authoritative final usage
                if event_usage:
                    if event_usage.get("cost_usd") is not None:
                        usage["cost_usd"] = event_usage["cost_usd"]
                    if event_usage.get("context_window"):
                        usage["context_window"] = event_usage["context_window"]
                    usage["input_tokens"] = (
                        event_usage.get("input_tokens", 0)
                        + event_usage.get("cache_read", 0)
                        + event_usage.get("cache_creation", 0)
                    )
                    usage["output_tokens"] = event_usage.get("output_tokens", 0)
                continue

            # Extract usage from assistant events (before skipping on empty text)
            if event_usage and kind != "ignore":
                # input_tokens = total context fill for this turn
                usage["input_tokens"] = (
                    event_usage.get("input_tokens", 0)
                    + event_usage.get("cache_read", 0)
                    + event_usage.get("cache_creation", 0)
                )
                usage["output_tokens"] += event_usage.get("output_tokens", 0)

            if kind == "ignore" or not text:
                continue

            accumulated += text
            info.accumulated_output = accumulated
            info.last_activity_at = datetime.now(timezone.utc).isoformat()

            # Update card (debounced)
            now = loop.time()
            if now - last_update >= _UPDATE_INTERVAL:
                await _update_agent_card(
                    info.card_id,
                    info.study,
                    server,
                    {
                        "output": accumulated,
                        "last_activity_at": info.last_activity_at,
                        "usage": usage,
                    },
                    title=card_title,
                )
                last_update = now

        # Wait for process exit
        returncode = await loop.run_in_executor(None, proc.wait)
        completed_at = datetime.now(timezone.utc).isoformat()
        info.completed_at = completed_at

        # Calculate duration
        duration: float | None = None
        if info.started_at:
            start_dt = datetime.fromisoformat(info.started_at)
            end_dt = datetime.fromisoformat(completed_at)
            duration = (end_dt - start_dt).total_seconds()

        if returncode == 0:
            info.status = "completed"
            # Prefer final_result (clean text without tool-use indicators)
            display = final_result or accumulated
            if not display.strip():
                display = "*Agent completed with no output.*"
            await _update_agent_card(
                info.card_id,
                info.study,
                server,
                {
                    "status": "completed",
                    "output": display,
                    "completed_at": completed_at,
                    "duration": duration,
                    "usage": usage,
                },
                title=card_title,
            )
            await server._broadcast(
                {
                    "type": "agent.completed",
                    "study": info.study,
                    "task": info.task,
                    "card_id": info.card_id,
                }
            )
        else:
            info.status = "failed"
            # stderr is merged into stdout (subprocess.STDOUT), so error
            # details are already captured in the accumulated output.
            info.error = f"Process exited with code {returncode}"
            error_output = accumulated + f"\n\n---\n**Error:** {info.error}"
            await _update_agent_card(
                info.card_id,
                info.study,
                server,
                {
                    "status": "failed",
                    "output": error_output,
                    "completed_at": completed_at,
                    "duration": duration,
                    "error": info.error,
                    "usage": usage,
                },
                title=card_title,
            )
            await server._broadcast(
                {
                    "type": "agent.failed",
                    "study": info.study,
                    "task": info.task,
                    "card_id": info.card_id,
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
        completed_at = datetime.now(timezone.utc).isoformat()
        info.status = "failed"
        info.error = f"Timed out after {_DISPATCH_TIMEOUT}s"
        info.completed_at = completed_at

        duration = None
        if info.started_at:
            start_dt = datetime.fromisoformat(info.started_at)
            end_dt = datetime.fromisoformat(completed_at)
            duration = (end_dt - start_dt).total_seconds()

        timeout_output = (
            accumulated + f"\n\n---\n**Timed out** after {_DISPATCH_TIMEOUT}s"
        )
        await _update_agent_card(
            info.card_id,
            info.study,
            server,
            {
                "status": "failed",
                "output": timeout_output,
                "completed_at": completed_at,
                "duration": duration,
                "error": info.error,
                "usage": usage,
            },
            title=card_title,
        )
        await server._broadcast(
            {
                "type": "agent.failed",
                "study": info.study,
                "task": info.task,
                "card_id": info.card_id,
                "error": info.error,
            }
        )

    except Exception as e:
        info.status = "failed"
        info.error = str(e)
        logger.exception(f"Monitor error for dispatch '{info.task}'")
        # Update the stored card so it doesn't stay "running" forever
        completed_at = datetime.now(timezone.utc).isoformat()
        info.completed_at = completed_at
        duration: float | None = None
        if info.started_at:
            start_dt = datetime.fromisoformat(info.started_at)
            end_dt = datetime.fromisoformat(completed_at)
            duration = (end_dt - start_dt).total_seconds()
        try:
            await _update_agent_card(
                info.card_id,
                info.study,
                server,
                {
                    "status": "failed",
                    "output": accumulated + f"\n\n---\n**Error:** {info.error}",
                    "completed_at": completed_at,
                    "duration": duration,
                    "error": info.error,
                    "usage": usage,
                },
                title=card_title,
            )
        except Exception:
            logger.debug("Failed to update card after monitor error")

    finally:
        # Clean up paper workspace copies if one was created
        paper_ws = info.extra.get("paper_workspace")
        paper_copies = info.extra.get("paper_copies")
        if paper_ws and paper_copies:
            _cleanup_paper_workspace(Path(paper_ws), paper_copies)
        # Clean up sandbox copy if one was created
        sandbox = info.extra.get("sandbox")
        if sandbox:
            _cleanup_sandbox(Path(sandbox))


async def cancel_agent(card_id: str, server: DisplayServer) -> bool:
    """Cancel a running agent by card_id."""
    info = server._dispatches.get(card_id)
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

    completed_at = datetime.now(timezone.utc).isoformat()
    info.status = "cancelled"
    info.completed_at = completed_at

    duration: float | None = None
    if info.started_at:
        start_dt = datetime.fromisoformat(info.started_at)
        end_dt = datetime.fromisoformat(completed_at)
        duration = (end_dt - start_dt).total_seconds()

    # Clean up paper workspace copies if one was created
    paper_ws = info.extra.get("paper_workspace")
    paper_copies = info.extra.get("paper_copies")
    if paper_ws and paper_copies:
        _cleanup_paper_workspace(Path(paper_ws), paper_copies)
    # Clean up sandbox copy if one was created
    sandbox = info.extra.get("sandbox")
    if sandbox:
        _cleanup_sandbox(Path(sandbox))

    # Update card to cancelled state — preserve accumulated output
    config = _TASK_CONFIG.get(info.task, ("", "", ""))
    _, card_title, _ = config
    preserved = info.accumulated_output or ""
    if preserved.strip():
        cancel_output = preserved + "\n\n---\n*Cancelled by user.*"
    else:
        cancel_output = "*Cancelled by user.*"
    await _update_agent_card(
        card_id,
        info.study,
        server,
        {
            "status": "failed",
            "output": cancel_output,
            "completed_at": completed_at,
            "duration": duration,
            "error": "Cancelled by user",
        },
        title=card_title,
    )

    await server._broadcast(
        {
            "type": "agent.failed",
            "study": info.study,
            "task": info.task,
            "card_id": card_id,
            "error": "Cancelled by user",
        }
    )
    return True


def get_agent_status(card_id: str, server: DisplayServer) -> dict[str, Any] | None:
    """Get the status of an agent by card_id."""
    info = server._dispatches.get(card_id)
    if info is None:
        return None
    return {
        "status": info.status,
        "card_id": info.card_id,
        "study": info.study,
        "task": info.task,
        "model": info.model,
        "pid": info.pid,
        "error": info.error,
        "started_at": info.started_at,
        "completed_at": info.completed_at,
        "last_activity_at": info.last_activity_at,
    }


def reconcile_orphaned_agents(server: DisplayServer) -> int:
    """Fix agent cards stuck in 'running' state with no backing process.

    Called on server startup to clean up cards orphaned by previous crashes
    or restarts. Returns the number of cards fixed.
    """
    from m4.vitrine._types import CardType

    if not server.study_manager:
        return 0

    fixed = 0
    for card in server.study_manager.list_all_cards():
        if card.card_type != CardType.AGENT:
            continue
        status = card.preview.get("status", "pending") if card.preview else "pending"
        if status != "running":
            continue
        # This card claims to be running but we have no dispatch for it
        if card.card_id in server._dispatches:
            continue
        # Fix: mark as failed in the store
        new_preview = dict(card.preview)
        new_preview["status"] = "failed"
        new_preview["error"] = "Server restarted while agent was running"
        _, store = server.study_manager.get_or_create_study(card.study)
        if store:
            store.update_card(card.card_id, preview=new_preview)
        fixed += 1
        logger.info(f"Reconciled orphaned agent card: {card.card_id}")
    return fixed


def cleanup_dispatches(server: DisplayServer) -> None:
    """Terminate all running dispatches. Called on server shutdown."""
    for card_id, info in server._dispatches.items():
        if info.status == "running" and info.process is not None:
            try:
                info.process.terminate()
            except OSError:
                pass
            info.status = "cancelled"
        # Clean up any paper workspace copies
        paper_ws = info.extra.get("paper_workspace")
        paper_copies = info.extra.get("paper_copies")
        if paper_ws and paper_copies:
            _cleanup_paper_workspace(Path(paper_ws), paper_copies)
        # Clean up any sandbox copies
        sandbox = info.extra.get("sandbox")
        if sandbox:
            _cleanup_sandbox(Path(sandbox))
    server._dispatches.clear()


def _is_pid_alive(pid: int) -> bool:
    """Check if a process with the given PID is alive."""
    from m4.vitrine._utils import is_pid_alive

    return is_pid_alive(pid)


_WATCHDOG_INTERVAL = 30  # seconds


async def _dispatch_watchdog(server: DisplayServer) -> None:
    """Periodic safety net: detect dead PIDs that the stream monitor missed."""
    while True:
        await asyncio.sleep(_WATCHDOG_INTERVAL)
        for info in list(server._dispatches.values()):
            if info.status != "running" or info.pid is None:
                continue
            if _is_pid_alive(info.pid):
                continue
            # PID is dead but monitor hasn't caught it yet
            if info.monitor_task and not info.monitor_task.done():
                # Give the monitor a moment to catch up
                continue
            # Monitor is done or absent — force-fail the card
            info.status = "failed"
            info.error = "Process exited unexpectedly"
            completed_at = datetime.now(timezone.utc).isoformat()
            info.completed_at = completed_at
            duration = None
            if info.started_at:
                start_dt = datetime.fromisoformat(info.started_at)
                end_dt = datetime.fromisoformat(completed_at)
                duration = (end_dt - start_dt).total_seconds()
            config = _TASK_CONFIG.get(info.task, ("", "", ""))
            _, card_title, _ = config
            output = (
                info.accumulated_output
                + "\n\n---\n**Error:** Process exited unexpectedly"
            )
            await _update_agent_card(
                info.card_id,
                info.study,
                server,
                {
                    "status": "failed",
                    "output": output,
                    "completed_at": completed_at,
                    "duration": duration,
                    "error": info.error,
                },
                title=card_title,
            )
            await server._broadcast(
                {
                    "type": "agent.failed",
                    "study": info.study,
                    "task": info.task,
                    "card_id": info.card_id,
                    "error": info.error,
                }
            )
            logger.warning(
                f"Watchdog: agent {info.card_id} PID {info.pid} dead, marked failed"
            )
