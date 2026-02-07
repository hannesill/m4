"""Export display runs as self-contained HTML or JSON artifacts.

Produces reproducible research artifacts that can be shared, archived,
or opened without a running display server.

Export formats:
- HTML: Self-contained file with inlined CSS, JS (Plotly, marked),
  and all artifact data. Opens in any browser without a server.
- JSON: Zip archive with card index, metadata, and raw artifact files.
"""

from __future__ import annotations

import io
import json
import logging
import zipfile
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

import duckdb

from m4.display._types import CardDescriptor, CardType
from m4.display.artifacts import _serialize_card
from m4.display.run_manager import RunManager

logger = logging.getLogger(__name__)

# Maximum rows to include in HTML table exports
_MAX_HTML_TABLE_ROWS = 10_000

_STATIC_DIR = Path(__file__).parent / "static"


def export_html(
    run_manager: RunManager,
    output_path: str | Path,
    run_id: str | None = None,
) -> Path:
    """Export a run (or all runs) as a self-contained HTML file.

    The exported file includes inlined CSS, vendored JS (Plotly, marked),
    and all artifact data. It opens in any browser without a server.

    Args:
        run_manager: The RunManager containing run data.
        output_path: Path to write the HTML file.
        run_id: Specific run label to export, or None for all runs.

    Returns:
        Path to the written file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Gather cards and metadata
    cards = run_manager.list_all_cards(run_id=run_id)
    runs = run_manager.list_runs()

    if run_id:
        runs = [r for r in runs if r["label"] == run_id]

    # Build the HTML document
    html = _build_html_document(cards, runs, run_manager, run_id)
    output_path.write_text(html, encoding="utf-8")

    logger.debug(f"Exported HTML: {output_path} ({len(cards)} cards)")
    return output_path


def export_json(
    run_manager: RunManager,
    output_path: str | Path,
    run_id: str | None = None,
) -> Path:
    """Export a run (or all runs) as a JSON zip archive.

    The archive contains:
    - meta.json: Export metadata (timestamp, run info)
    - cards.json: All card descriptors
    - artifacts/: Raw artifact files (parquet, json, svg, png)

    Args:
        run_manager: The RunManager containing run data.
        output_path: Path to write the zip file.
        run_id: Specific run label to export, or None for all runs.

    Returns:
        Path to the written file.
    """
    output_path = Path(output_path)
    if not str(output_path).endswith(".zip"):
        output_path = output_path.with_suffix(".zip")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cards = run_manager.list_all_cards(run_id=run_id)
    runs = run_manager.list_runs()
    if run_id:
        runs = [r for r in runs if r["label"] == run_id]

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Export metadata
        meta = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "format_version": "1.0",
            "run_id": run_id,
            "runs": runs,
            "card_count": len(cards),
        }
        zf.writestr("meta.json", json.dumps(meta, indent=2, default=str))

        # Card descriptors
        card_dicts = [_serialize_card(c) for c in cards]
        zf.writestr("cards.json", json.dumps(card_dicts, indent=2, default=str))

        # Artifact files
        seen_artifacts: set[str] = set()
        for card in cards:
            if not card.artifact_id or card.artifact_id in seen_artifacts:
                continue
            seen_artifacts.add(card.artifact_id)

            store = run_manager.get_store_for_card(card.card_id)
            if not store:
                continue

            for ext in ("parquet", "json", "svg", "png"):
                artifact_path = store._artifacts_dir / f"{card.artifact_id}.{ext}"
                if artifact_path.exists():
                    arcname = f"artifacts/{card.artifact_id}.{ext}"
                    zf.write(artifact_path, arcname)

    logger.debug(f"Exported JSON zip: {output_path} ({len(cards)} cards)")
    return output_path


def export_html_string(
    run_manager: RunManager,
    run_id: str | None = None,
) -> str:
    """Export as HTML and return the string (for server endpoint streaming).

    Args:
        run_manager: The RunManager containing run data.
        run_id: Specific run label to export, or None for all runs.

    Returns:
        HTML string.
    """
    cards = run_manager.list_all_cards(run_id=run_id)
    runs = run_manager.list_runs()
    if run_id:
        runs = [r for r in runs if r["label"] == run_id]
    return _build_html_document(cards, runs, run_manager, run_id)


def export_json_bytes(
    run_manager: RunManager,
    run_id: str | None = None,
) -> bytes:
    """Export as JSON zip and return bytes (for server endpoint streaming).

    Args:
        run_manager: The RunManager containing run data.
        run_id: Specific run label to export, or None for all runs.

    Returns:
        Zip file bytes.
    """
    cards = run_manager.list_all_cards(run_id=run_id)
    runs = run_manager.list_runs()
    if run_id:
        runs = [r for r in runs if r["label"] == run_id]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        meta = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "format_version": "1.0",
            "run_id": run_id,
            "runs": runs,
            "card_count": len(cards),
        }
        zf.writestr("meta.json", json.dumps(meta, indent=2, default=str))

        card_dicts = [_serialize_card(c) for c in cards]
        zf.writestr("cards.json", json.dumps(card_dicts, indent=2, default=str))

        seen_artifacts: set[str] = set()
        for card in cards:
            if not card.artifact_id or card.artifact_id in seen_artifacts:
                continue
            seen_artifacts.add(card.artifact_id)

            store = run_manager.get_store_for_card(card.card_id)
            if not store:
                continue

            for ext in ("parquet", "json", "svg", "png"):
                artifact_path = store._artifacts_dir / f"{card.artifact_id}.{ext}"
                if artifact_path.exists():
                    arcname = f"artifacts/{card.artifact_id}.{ext}"
                    zf.write(artifact_path, arcname)

    return buf.getvalue()


# --- HTML Generation ---


def _build_html_document(
    cards: list[CardDescriptor],
    runs: list[dict[str, Any]],
    run_manager: RunManager,
    run_id: str | None,
) -> str:
    """Build a self-contained HTML document with all cards inlined."""
    title = f"M4 Export — {run_id}" if run_id else "M4 Export — All Runs"
    export_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Load vendored JS
    plotly_js = _load_vendored_js("plotly.min.js")
    marked_js = _load_vendored_js("marked.min.js")

    # Build card HTML
    cards_html = []
    current_run = None
    for card in cards:
        # Insert run separator if run changed (in "all runs" mode)
        if not run_id and card.run_id and card.run_id != current_run:
            current_run = card.run_id
            run_meta = _find_run(runs, card.run_id)
            sep_label = card.run_id
            if run_meta and run_meta.get("start_time"):
                sep_label += f" &middot; {_format_date(run_meta['start_time'])}"
            cards_html.append(f'<div class="run-separator">{escape(sep_label)}</div>')

        if card.card_type == CardType.SECTION:
            cards_html.append(
                f'<div class="section-divider">{escape(card.title or "")}</div>'
            )
        else:
            cards_html.append(_render_card_html(card, run_manager))

    cards_block = "\n".join(cards_html)

    # Run summary for header
    run_summary = ""
    if run_id:
        run_meta = _find_run(runs, run_id)
        if run_meta:
            run_summary = (
                f'<div class="export-run-info">'
                f"<strong>{escape(run_id)}</strong>"
                f" &middot; {len(cards)} cards"
                f" &middot; {_format_date(run_meta.get('start_time', ''))}"
                f"</div>"
            )
    else:
        run_summary = (
            f'<div class="export-run-info">'
            f"{len(runs)} runs &middot; {len(cards)} cards"
            f"</div>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escape(title)}</title>
{_EXPORT_CSS}
{f"<script>{plotly_js}</script>" if plotly_js else ""}
{f"<script>{marked_js}</script>" if marked_js else ""}
</head>
<body>

<div class="export-header">
  <div class="export-header-left">
    <h1>M4 Display</h1>
    {run_summary}
  </div>
  <div class="export-header-right">
    <span class="export-timestamp">Exported {export_time}</span>
  </div>
</div>

<div class="feed">
{cards_block if cards_block else '<div class="empty-state">No cards to export</div>'}
</div>

<div class="export-footer">
  M4 Display Export &middot; {len(cards)} cards &middot; {export_time}
</div>

<script>
{_EXPORT_JS}
</script>
</body>
</html>"""


def _render_card_html(card: CardDescriptor, run_manager: RunManager) -> str:
    """Render a single card as self-contained HTML."""
    # Card chrome
    title_html = f"<h3>{escape(card.title)}</h3>" if card.title else ""
    desc_html = (
        f'<div class="card-description">{escape(card.description)}</div>'
        if card.description
        else ""
    )
    ts_html = (
        f'<span class="card-timestamp">{_format_timestamp(card.timestamp)}</span>'
        if card.timestamp
        else ""
    )

    # Provenance
    prov_html = ""
    if card.provenance:
        prov_parts = []
        if card.provenance.source:
            prov_parts.append(f"source: {escape(card.provenance.source)}")
        if card.provenance.dataset:
            prov_parts.append(f"dataset: {escape(card.provenance.dataset)}")
        if card.provenance.query:
            prov_parts.append(f"query: {escape(card.provenance.query[:200])}")
        if card.provenance.timestamp:
            prov_parts.append(_format_timestamp(card.provenance.timestamp))
        if prov_parts:
            prov_html = (
                f'<div class="card-provenance">{" &middot; ".join(prov_parts)}</div>'
            )

    # Body
    body_html = _render_card_body(card, run_manager)

    return f"""<div class="card" data-card-type="{card.card_type.value}">
  <div class="card-header">
    <div class="card-header-left">{title_html}{desc_html}</div>
    <div class="card-header-right">{ts_html}</div>
  </div>
  <div class="card-body">{body_html}</div>
  {prov_html}
</div>"""


def _render_card_body(card: CardDescriptor, run_manager: RunManager) -> str:
    """Render card body content based on card type."""
    if card.card_type == CardType.TABLE:
        return _render_table_html(card, run_manager)
    elif card.card_type == CardType.PLOTLY:
        return _render_plotly_html(card)
    elif card.card_type == CardType.IMAGE:
        return _render_image_html(card)
    elif card.card_type == CardType.MARKDOWN:
        return _render_markdown_html(card)
    elif card.card_type == CardType.KEYVALUE:
        return _render_keyvalue_html(card)
    else:
        return f"<pre>{escape(json.dumps(card.preview, indent=2, default=str))}</pre>"


def _render_table_html(card: CardDescriptor, run_manager: RunManager) -> str:
    """Render a table card as full HTML table from Parquet artifact."""
    store = run_manager.get_store_for_card(card.card_id)
    if not store or not card.artifact_id:
        # Fall back to preview data
        return _render_table_from_preview(card)

    parquet_path = store._artifacts_dir / f"{card.artifact_id}.parquet"
    if not parquet_path.exists():
        return _render_table_from_preview(card)

    try:
        con = duckdb.connect(":memory:")
        try:
            total = con.execute(
                f"SELECT COUNT(*) FROM read_parquet('{parquet_path}')"
            ).fetchone()[0]

            truncated = total > _MAX_HTML_TABLE_ROWS
            query = f"SELECT * FROM read_parquet('{parquet_path}')"
            if truncated:
                query += f" LIMIT {_MAX_HTML_TABLE_ROWS}"

            result = con.execute(query)
            columns = [desc[0] for desc in result.description]
            rows = result.fetchall()
        finally:
            con.close()

        # Build HTML table
        header = "".join(f"<th>{escape(str(c))}</th>" for c in columns)
        body_rows = []
        for row in rows:
            cells = "".join(f"<td>{escape(_format_cell(v))}</td>" for v in row)
            body_rows.append(f"<tr>{cells}</tr>")

        shape_info = f"{total} rows &times; {len(columns)} columns"
        if truncated:
            shape_info += f" (showing first {_MAX_HTML_TABLE_ROWS:,})"

        return f"""<div class="table-info">{shape_info}</div>
<div class="table-wrapper">
<table><thead><tr>{header}</tr></thead>
<tbody>{"".join(body_rows)}</tbody></table>
</div>"""
    except Exception as e:
        logger.debug(f"Failed to read parquet for export: {e}")
        return _render_table_from_preview(card)


def _render_table_from_preview(card: CardDescriptor) -> str:
    """Render table from preview data (fallback when Parquet unavailable)."""
    preview = card.preview
    columns = preview.get("columns", [])
    rows = preview.get("preview_rows", [])
    shape = preview.get("shape", [0, 0])

    header = "".join(f"<th>{escape(str(c))}</th>" for c in columns)
    body_rows = []
    for row in rows:
        cells = "".join(f"<td>{escape(_format_cell(v))}</td>" for v in row)
        body_rows.append(f"<tr>{cells}</tr>")

    shape_info = f"{shape[0]} rows &times; {shape[1]} columns"
    if len(rows) < shape[0]:
        shape_info += f" (preview: first {len(rows)})"

    return f"""<div class="table-info">{shape_info}</div>
<div class="table-wrapper">
<table><thead><tr>{header}</tr></thead>
<tbody>{"".join(body_rows)}</tbody></table>
</div>"""


def _render_plotly_html(card: CardDescriptor) -> str:
    """Render a Plotly chart as an interactive div (requires inlined plotly.js)."""
    spec = card.preview.get("spec", {})
    spec_json = json.dumps(spec, default=str)
    div_id = f"plotly-{card.card_id}"
    return f"""<div id="{div_id}" class="plotly-export-container"></div>
<script class="plotly-init">
(function() {{
  var spec = {spec_json};
  var el = document.getElementById('{div_id}');
  if (typeof Plotly !== 'undefined' && el) {{
    var data = spec.data || [];
    var layout = spec.layout || {{}};
    layout.autosize = true;
    Plotly.newPlot(el, data, layout, {{responsive: true, displayModeBar: false}});
  }} else if (el) {{
    el.textContent = 'Plotly.js not available — chart data exported in JSON.';
  }}
}})();
</script>"""


def _render_image_html(card: CardDescriptor) -> str:
    """Render an image card as inline base64."""
    preview = card.preview
    data = preview.get("data", "")
    fmt = preview.get("format", "svg")

    if fmt == "svg":
        mime = "image/svg+xml"
    else:
        mime = f"image/{fmt}"

    return (
        f'<div class="image-container">'
        f'<img src="data:{mime};base64,{data}" alt="{escape(card.title or "Figure")}" '
        f'style="max-width: 100%; height: auto;" />'
        f"</div>"
    )


def _render_markdown_html(card: CardDescriptor) -> str:
    """Render markdown as HTML (uses marked.js in the export, fallback to escaped text)."""
    text = card.preview.get("text", "")
    div_id = f"md-{card.card_id}"
    return f"""<div id="{div_id}" class="markdown-export">{escape(text)}</div>
<script class="md-init">
(function() {{
  var el = document.getElementById('{div_id}');
  if (typeof marked !== 'undefined' && el) {{
    el.innerHTML = marked.parse({json.dumps(text)});
  }}
}})();
</script>"""


def _render_keyvalue_html(card: CardDescriptor) -> str:
    """Render key-value pairs as a definition list."""
    items = card.preview.get("items", {})
    rows = "".join(
        f"<tr><td class='kv-key'>{escape(str(k))}</td>"
        f"<td class='kv-value'>{escape(str(v))}</td></tr>"
        for k, v in items.items()
    )
    return f'<table class="kv-table"><tbody>{rows}</tbody></table>'


# --- Helpers ---


def _load_vendored_js(filename: str) -> str:
    """Load a vendored JS file, returning empty string if not found."""
    path = _STATIC_DIR / "vendor" / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _find_run(runs: list[dict[str, Any]], label: str) -> dict[str, Any] | None:
    """Find a run by label in a list of run dicts."""
    for r in runs:
        if r.get("label") == label:
            return r
    return None


def _format_timestamp(iso_str: str) -> str:
    """Format an ISO timestamp for display."""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return iso_str[:16]


def _format_date(iso_str: str) -> str:
    """Format an ISO timestamp as a date string."""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%b %d, %Y %H:%M")
    except (ValueError, TypeError):
        return iso_str[:10]


def _format_cell(value: Any) -> str:
    """Format a cell value for HTML display."""
    if value is None:
        return ""
    if isinstance(value, float):
        if value != value:  # NaN check
            return ""
        if value == int(value) and abs(value) < 1e15:
            return str(int(value))
        return f"{value:.4g}"
    return str(value)


# --- CSS for Export ---

_EXPORT_CSS = """<style>
  :root {
    --bg: #ffffff;
    --bg-card: #f8f9fa;
    --bg-header: #f0f1f3;
    --text: #1a1a2e;
    --text-muted: #6c757d;
    --border: #dee2e6;
    --accent: #4361ee;
    --font: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;
    --mono: 'SF Mono', 'Fira Code', 'Fira Mono', Menlo, Consolas, monospace;
    --radius: 8px;
    --shadow: 0 1px 3px rgba(0,0,0,0.08);
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    font-family: var(--font);
    background: var(--bg);
    color: var(--text);
    line-height: 1.5;
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 24px;
  }

  .export-header {
    padding: 20px 0;
    border-bottom: 1px solid var(--border);
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .export-header h1 {
    font-size: 16px;
    font-weight: 600;
    letter-spacing: -0.3px;
  }

  .export-run-info {
    font-size: 13px;
    color: var(--text-muted);
    margin-top: 4px;
  }

  .export-timestamp {
    font-size: 12px;
    color: var(--text-muted);
  }

  .feed {
    padding-bottom: 40px;
  }

  .card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    margin-bottom: 16px;
    box-shadow: var(--shadow);
    overflow: hidden;
    page-break-inside: avoid;
  }

  .card-header {
    padding: 12px 16px;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: var(--bg-header);
  }

  .card-header h3 {
    font-size: 14px;
    font-weight: 600;
  }

  .card-description {
    font-size: 12px;
    color: var(--text-muted);
    margin-top: 2px;
  }

  .card-timestamp {
    font-size: 11px;
    color: var(--text-muted);
    white-space: nowrap;
  }

  .card-body {
    padding: 12px 16px;
  }

  .card-provenance {
    padding: 6px 16px;
    font-size: 11px;
    color: var(--text-muted);
    border-top: 1px solid var(--border);
    background: var(--bg-header);
  }

  /* Tables */
  .table-info {
    font-size: 12px;
    color: var(--text-muted);
    margin-bottom: 8px;
  }

  .table-wrapper {
    overflow-x: auto;
    max-height: 600px;
    overflow-y: auto;
  }

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
    font-family: var(--mono);
  }

  th {
    background: var(--bg-header);
    position: sticky;
    top: 0;
    padding: 6px 10px;
    text-align: left;
    font-weight: 600;
    border-bottom: 2px solid var(--border);
    white-space: nowrap;
  }

  td {
    padding: 4px 10px;
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
    max-width: 300px;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  tr:hover td { background: rgba(67, 97, 238, 0.04); }

  /* Key-Value */
  .kv-table {
    width: auto;
  }

  .kv-key {
    font-weight: 600;
    padding-right: 24px;
    white-space: nowrap;
    color: var(--text-muted);
  }

  .kv-value {
    font-family: var(--mono);
  }

  /* Plotly */
  .plotly-export-container {
    width: 100%;
    min-height: 300px;
  }

  /* Images */
  .image-container {
    text-align: center;
  }

  .image-container img {
    max-width: 100%;
    height: auto;
  }

  /* Markdown */
  .markdown-export {
    font-size: 14px;
    line-height: 1.6;
  }

  .markdown-export h1, .markdown-export h2, .markdown-export h3 {
    margin: 12px 0 6px;
  }

  .markdown-export p { margin: 6px 0; }

  .markdown-export pre {
    background: var(--bg-header);
    padding: 10px;
    border-radius: 4px;
    overflow-x: auto;
    font-family: var(--mono);
    font-size: 12px;
  }

  .markdown-export code {
    font-family: var(--mono);
    font-size: 0.9em;
    background: var(--bg-header);
    padding: 1px 4px;
    border-radius: 3px;
  }

  .markdown-export pre code {
    background: none;
    padding: 0;
  }

  /* Section dividers */
  .section-divider {
    text-align: center;
    font-size: 13px;
    font-weight: 600;
    color: var(--text-muted);
    padding: 16px 0 8px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 16px;
  }

  /* Run separators */
  .run-separator {
    font-size: 12px;
    font-weight: 600;
    color: var(--accent);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding: 20px 0 8px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 12px;
  }

  .empty-state {
    text-align: center;
    color: var(--text-muted);
    padding: 60px 0;
    font-size: 14px;
  }

  .export-footer {
    text-align: center;
    font-size: 11px;
    color: var(--text-muted);
    padding: 24px 0;
    border-top: 1px solid var(--border);
  }

  /* Print styles */
  @media print {
    body {
      max-width: none;
      padding: 0;
      font-size: 10pt;
    }

    .export-header {
      padding: 10px 0;
      margin-bottom: 10px;
    }

    .card {
      box-shadow: none;
      border: 1px solid #ccc;
      margin-bottom: 10px;
      page-break-inside: avoid;
    }

    .card-body { padding: 8px 12px; }

    .table-wrapper {
      max-height: none;
      overflow: visible;
    }

    table { font-size: 9pt; }
    th, td { padding: 3px 6px; }

    .plotly-export-container {
      min-height: 200px;
    }

    .export-footer {
      position: fixed;
      bottom: 0;
      left: 0;
      right: 0;
      background: white;
    }
  }
</style>"""


# --- JS for Export (minimal — just init Plotly charts and render markdown) ---

_EXPORT_JS = """
// Initialize Plotly charts after page load
document.addEventListener('DOMContentLoaded', function() {
  // Plotly init scripts are already inline — they self-execute.
  // Marked.js init scripts are already inline — they self-execute.
});
"""
