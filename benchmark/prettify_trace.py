#!/usr/bin/env python3
"""Prettify agent trace.jsonl files into readable HTML.

Usage:
    python benchmark/prettify_trace.py benchmark/results/*/trace.jsonl
    python benchmark/prettify_trace.py trace.jsonl -o my_trace.html
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path


def _escape(text: str) -> str:
    return html.escape(text)


def _format_tokens_summary(usage: dict) -> str:
    """Format aggregate token usage for the header bar.

    The API reports input_tokens as *non-cached* input only.
    Total context = input_tokens + cache_read + cache_create.
    """
    non_cached = usage.get("input_tokens", 0)
    cache_read = usage.get("cache_read_input_tokens", 0)
    cache_create = usage.get("cache_creation_input_tokens", 0)
    total_in = non_cached + cache_read + cache_create
    out = usage.get("output_tokens", 0)

    parts = []
    if total_in:
        parts.append(f"in: {total_in:,}")
        # Breakdown only if caching was used
        if cache_read or cache_create:
            sub = []
            if cache_read:
                sub.append(f"cache read {cache_read:,}")
            if cache_create:
                sub.append(f"cache write {cache_create:,}")
            if non_cached:
                sub.append(f"uncached {non_cached:,}")
            parts.append(f"({', '.join(sub)})")
    if out:
        parts.append(f"out: {out:,}")
    return " ".join(parts) if parts else ""


def _format_turn_context(usage: dict) -> str:
    """Format per-turn context window size (how much the model saw)."""
    non_cached = usage.get("input_tokens", 0)
    cache_read = usage.get("cache_read_input_tokens", 0)
    cache_create = usage.get("cache_creation_input_tokens", 0)
    total_ctx = non_cached + cache_read + cache_create
    if total_ctx:
        return f"ctx: {total_ctx:,} tokens"
    return ""


def _render_tool_input(name: str, inp: dict) -> str:
    """Render tool input in a compact, readable way."""
    if name == "Bash":
        cmd = inp.get("command", "")
        desc = inp.get("description", "")
        label = f"<span class='tool-desc'>{_escape(desc)}</span><br>" if desc else ""
        return f"{label}<pre class='code'>{_escape(cmd)}</pre>"
    elif name == "Read":
        return f"<code>{_escape(inp.get('file_path', ''))}</code>"
    elif name in ("Glob", "Grep"):
        pattern = inp.get("pattern", "")
        path = inp.get("path", "")
        extra = f" in <code>{_escape(path)}</code>" if path else ""
        return f"<code>{_escape(pattern)}</code>{extra}"
    elif name == "Edit":
        fp = inp.get("file_path", "")
        old = inp.get("old_string", "")[:200]
        return f"<code>{_escape(fp)}</code><pre class='code'>{_escape(old)}{'...' if len(inp.get('old_string', '')) > 200 else ''}</pre>"
    elif name == "Write":
        fp = inp.get("file_path", "")
        content = inp.get("content", "")
        preview = content[:300]
        return f"<code>{_escape(fp)}</code> ({len(content)} chars)<pre class='code'>{_escape(preview)}{'...' if len(content) > 300 else ''}</pre>"
    elif name == "Skill":
        return f"<code>{_escape(inp.get('skill', ''))}</code>"
    else:
        raw = json.dumps(inp, indent=2)
        if len(raw) > 500:
            raw = raw[:500] + "\n..."
        return f"<pre class='code'>{_escape(raw)}</pre>"


def _truncate_result(text: str, limit: int = 2000) -> str:
    if len(text) <= limit:
        return _escape(text)
    return (
        _escape(text[:limit])
        + f"\n<span class='truncated'>... ({len(text) - limit} chars truncated)</span>"
    )


def _merge_assistant_events(events: list[dict]) -> list[dict]:
    """Merge consecutive assistant events that belong to the same API call.

    Claude Code's stream-json format emits one assistant event per content
    block (thinking, text, tool_use).  Events from the same API response
    carry identical usage dicts.  We merge them into a single event with
    all content blocks combined.
    """
    merged: list[dict] = []

    for evt in events:
        if evt.get("type") != "assistant":
            merged.append(evt)
            continue

        msg = evt.get("message", {})
        usage = msg.get("usage", {})
        content = msg.get("content", [])

        # Try to merge with the previous merged event
        if (
            merged
            and merged[-1].get("type") == "assistant"
            and merged[-1].get("message", {}).get("usage", {}) == usage
        ):
            merged[-1]["message"]["content"].extend(content)
        else:
            # Deep-copy enough to avoid mutating the original
            merged.append(
                {
                    "type": "assistant",
                    "message": {
                        "usage": usage,
                        "content": list(content),
                    },
                }
            )

    return merged


def convert_trace(trace_path: Path) -> str:
    """Convert a trace.jsonl file to an HTML string."""
    raw_events = []
    for line in trace_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw_events.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    # Extract metadata
    init_event = next(
        (
            e
            for e in raw_events
            if e.get("type") == "system" and e.get("subtype") == "init"
        ),
        {},
    )
    result_event = next((e for e in raw_events if e.get("type") == "result"), {})

    model = init_event.get("model", "unknown")

    duration_ms = result_event.get("duration_ms", 0)
    duration_s = duration_ms / 1000 if duration_ms else 0
    cost = result_event.get("total_cost_usd", 0)
    num_turns = result_event.get("num_turns", 0)
    final_result = result_event.get("result", "")
    result_usage = result_event.get("usage", {})
    is_error = result_event.get("is_error", False)

    # Merge duplicate assistant events (same API call, split per content block)
    events = _merge_assistant_events(raw_events)

    # Build tool-result lookup: tool_use_id -> content
    tool_results: dict[str, tuple[str, bool]] = {}
    for evt in events:
        if evt.get("type") == "user":
            content = evt.get("message", {}).get("content", [])
            if isinstance(content, list):
                for block in content:
                    if block.get("type") == "tool_result":
                        tid = block.get("tool_use_id", "")
                        text = block.get("content", "")
                        if isinstance(text, list):
                            text = "\n".join(
                                b.get("text", "")
                                for b in text
                                if b.get("type") == "text"
                            )
                        tool_results[tid] = (str(text), block.get("is_error", False))

    # Render conversation turns
    turns_html = []
    turn_num = 0

    for evt in events:
        etype = evt.get("type")

        if etype == "assistant":
            msg = evt.get("message", {})
            content = msg.get("content", [])
            if not content:
                continue

            turn_num += 1
            blocks_html = []

            for block in content:
                btype = block.get("type", "")

                if btype == "thinking":
                    thinking_text = block.get("thinking", "").strip()
                    if thinking_text:
                        blocks_html.append(f"""
                            <details class='thinking-block'>
                                <summary><span class='thinking-label'>Thinking</span></summary>
                                <div class='thinking-text'>{_escape(thinking_text)}</div>
                            </details>
                        """)

                elif btype == "text":
                    text = block.get("text", "").strip()
                    if text:
                        blocks_html.append(
                            f"<div class='text-block'>{_escape(text)}</div>"
                        )

                elif btype == "tool_use":
                    tool_name = block.get("name", "?")
                    tool_id = block.get("id", "")
                    tool_input = block.get("input", {})

                    input_html = _render_tool_input(tool_name, tool_input)

                    # Find matching result
                    result_text, is_err = tool_results.get(tool_id, ("", False))
                    result_class = "tool-error" if is_err else "tool-output"

                    result_html = ""
                    if result_text:
                        result_html = f"<div class='{result_class}'><pre>{_truncate_result(result_text)}</pre></div>"

                    blocks_html.append(f"""
                        <details class='tool-call' {"open" if tool_name == "Bash" else ""}>
                            <summary><span class='tool-name'>{_escape(tool_name)}</span></summary>
                            <div class='tool-input'>{input_html}</div>
                            {result_html}
                        </details>
                    """)

            if blocks_html:
                usage = msg.get("usage", {})
                ctx_str = _format_turn_context(usage)
                meta = f"<span class='turn-meta'>{ctx_str}</span>" if ctx_str else ""

                turns_html.append(f"""
                    <div class='turn assistant-turn'>
                        <div class='turn-header'>
                            <span class='turn-label'>Turn {turn_num}</span>
                            {meta}
                        </div>
                        <div class='turn-body'>{"".join(blocks_html)}</div>
                    </div>
                """)

        elif etype == "user":
            content = evt.get("message", {}).get("content", [])
            if isinstance(content, list):
                for block in content:
                    if block.get("type") == "text":
                        text = block.get("text", "").strip()
                        # Skip system reminders and very long skill injections
                        if text and not text.startswith("<system-reminder>"):
                            preview = text[:500]
                            if len(text) > 500:
                                preview += "..."
                            turns_html.append(f"""
                                <div class='turn user-turn'>
                                    <div class='turn-header'><span class='turn-label'>User / System</span></div>
                                    <div class='turn-body'><pre class='user-text'>{_escape(preview)}</pre></div>
                                </div>
                            """)

        elif etype == "rate_limit_event":
            info = evt.get("rate_limit_info", {})
            status = info.get("status", "unknown")
            rl_type = info.get("rateLimitType", "")
            if status == "allowed":
                # Just a rate-limit check, not actually throttled — skip
                pass
            else:
                label = f"Rate limit: {status}"
                if rl_type:
                    label += f" ({rl_type})"
                turns_html.append(f"<div class='event-badge'>{_escape(label)}</div>")

    # Final result
    result_class = "result-error" if is_error else "result-success"
    result_badge = "ERROR" if is_error else "SUCCESS"

    # Derive task name from directory
    task_name = trace_path.parent.name

    # Format token summary for header
    token_summary = _format_tokens_summary(result_usage)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trace: {_escape(task_name)}</title>
<style>
    :root {{
        --bg: #0d1117;
        --surface: #161b22;
        --border: #30363d;
        --text: #e6edf3;
        --text-muted: #8b949e;
        --accent: #58a6ff;
        --green: #3fb950;
        --red: #f85149;
        --orange: #d29922;
        --purple: #bc8cff;
        --code-bg: #0d1117;
    }}
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
        background: var(--bg);
        color: var(--text);
        line-height: 1.5;
        padding: 2rem;
        max-width: 960px;
        margin: 0 auto;
    }}
    h1 {{
        font-size: 1.4rem;
        font-weight: 600;
        margin-bottom: 0.5rem;
        color: var(--accent);
    }}
    .meta-bar {{
        display: flex;
        flex-wrap: wrap;
        gap: 1.5rem;
        padding: 1rem;
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 8px;
        margin-bottom: 1.5rem;
        font-size: 0.85rem;
    }}
    .meta-item {{ color: var(--text-muted); }}
    .meta-item strong {{ color: var(--text); }}
    .turn {{
        border: 1px solid var(--border);
        border-radius: 8px;
        margin-bottom: 0.75rem;
        overflow: hidden;
    }}
    .turn-header {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 0.5rem 1rem;
        background: var(--surface);
        border-bottom: 1px solid var(--border);
        font-size: 0.8rem;
    }}
    .turn-label {{ font-weight: 600; }}
    .turn-meta {{ color: var(--text-muted); font-size: 0.75rem; }}
    .turn-body {{ padding: 0.75rem 1rem; }}
    .assistant-turn {{ border-left: 3px solid var(--accent); }}
    .user-turn {{ border-left: 3px solid var(--orange); }}
    .text-block {{
        white-space: pre-wrap;
        word-wrap: break-word;
        margin-bottom: 0.5rem;
        font-size: 0.9rem;
    }}
    .thinking-block {{
        margin: 0.5rem 0;
        border: 1px solid var(--border);
        border-radius: 6px;
        border-left: 3px solid var(--purple);
        overflow: hidden;
    }}
    .thinking-block summary {{
        padding: 0.4rem 0.75rem;
        background: var(--surface);
        cursor: pointer;
        font-size: 0.85rem;
    }}
    .thinking-block summary:hover {{ background: #1c2128; }}
    .thinking-label {{
        color: var(--purple);
        font-weight: 600;
        font-size: 0.8rem;
    }}
    .thinking-text {{
        padding: 0.5rem 0.75rem;
        white-space: pre-wrap;
        word-wrap: break-word;
        font-size: 0.8rem;
        color: var(--text-muted);
        font-style: italic;
    }}
    .tool-call {{
        margin: 0.5rem 0;
        border: 1px solid var(--border);
        border-radius: 6px;
        overflow: hidden;
    }}
    .tool-call summary {{
        padding: 0.4rem 0.75rem;
        background: var(--surface);
        cursor: pointer;
        font-size: 0.85rem;
    }}
    .tool-call summary:hover {{ background: #1c2128; }}
    .tool-name {{
        font-weight: 600;
        color: var(--green);
        font-family: 'SF Mono', 'Fira Code', monospace;
    }}
    .tool-desc {{ color: var(--text-muted); font-style: italic; font-size: 0.8rem; }}
    .tool-input {{ padding: 0.5rem 0.75rem; }}
    .tool-output, .tool-error {{
        padding: 0.5rem 0.75rem;
        border-top: 1px solid var(--border);
        font-size: 0.8rem;
    }}
    .tool-output {{ background: rgba(63, 185, 80, 0.05); }}
    .tool-error {{ background: rgba(248, 81, 73, 0.08); color: var(--red); }}
    .tool-output pre, .tool-error pre {{
        white-space: pre-wrap;
        word-wrap: break-word;
        font-size: 0.8rem;
    }}
    pre.code {{
        background: var(--code-bg);
        padding: 0.5rem;
        border-radius: 4px;
        font-size: 0.8rem;
        overflow-x: auto;
        white-space: pre-wrap;
        word-wrap: break-word;
        font-family: 'SF Mono', 'Fira Code', monospace;
    }}
    pre.user-text {{
        font-size: 0.85rem;
        white-space: pre-wrap;
        word-wrap: break-word;
    }}
    code {{
        background: var(--code-bg);
        padding: 0.15rem 0.35rem;
        border-radius: 3px;
        font-size: 0.85rem;
        font-family: 'SF Mono', 'Fira Code', monospace;
    }}
    .truncated {{ color: var(--text-muted); font-style: italic; }}
    .event-badge {{
        display: inline-block;
        padding: 0.25rem 0.75rem;
        margin: 0.5rem 0;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 600;
        background: rgba(210, 153, 34, 0.15);
        color: var(--orange);
        border: 1px solid var(--orange);
    }}
    .final-result {{
        margin-top: 1.5rem;
        padding: 1rem;
        border-radius: 8px;
        border: 1px solid var(--border);
    }}
    .result-success {{ border-color: var(--green); background: rgba(63, 185, 80, 0.06); }}
    .result-error {{ border-color: var(--red); background: rgba(248, 81, 73, 0.06); }}
    .result-badge {{
        display: inline-block;
        padding: 0.15rem 0.5rem;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 700;
        margin-bottom: 0.5rem;
    }}
    .result-success .result-badge {{ background: var(--green); color: #000; }}
    .result-error .result-badge {{ background: var(--red); color: #fff; }}
    .final-result pre {{
        white-space: pre-wrap;
        word-wrap: break-word;
        font-size: 0.9rem;
        margin-top: 0.5rem;
    }}
</style>
</head>
<body>
<h1>{_escape(task_name)}</h1>
<div class='meta-bar'>
    <div class='meta-item'>Model: <strong>{_escape(model)}</strong></div>
    <div class='meta-item'>Turns: <strong>{num_turns}</strong></div>
    <div class='meta-item'>Duration: <strong>{duration_s:.1f}s</strong></div>
    <div class='meta-item'>Cost: <strong>${cost:.4f}</strong></div>
    <div class='meta-item'>Tokens: <strong>{token_summary or "n/a"}</strong></div>
</div>

{"".join(turns_html)}

<div class='final-result {result_class}'>
    <span class='result-badge'>{result_badge}</span>
    <pre>{_escape(str(final_result))}</pre>
</div>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="Prettify agent trace.jsonl into HTML")
    parser.add_argument("traces", nargs="+", type=Path, help="trace.jsonl file(s)")
    parser.add_argument(
        "-o", "--output", type=Path, help="Output path (only for single trace)"
    )
    args = parser.parse_args()

    for trace_path in args.traces:
        if not trace_path.exists():
            print(f"Skipping {trace_path}: not found", file=sys.stderr)
            continue

        html_content = convert_trace(trace_path)

        if args.output and len(args.traces) == 1:
            out_path = args.output
        else:
            out_path = trace_path.with_suffix(".html")

        out_path.write_text(html_content)
        print(f"  {out_path}")


if __name__ == "__main__":
    main()
