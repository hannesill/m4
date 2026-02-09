"""Export display studies as self-contained HTML or JSON artifacts.

Produces reproducible research artifacts that can be shared, archived,
or opened without a running display server.

Export formats:
- HTML: Self-contained file with inlined CSS, JS (Plotly, marked),
  and all artifact data. Opens in any browser without a server.
- JSON: Zip archive with card index, metadata, and raw artifact files.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import zipfile
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

import duckdb

from m4.vitrine._types import CardDescriptor, CardType
from m4.vitrine.artifacts import _serialize_card
from m4.vitrine.study_manager import StudyManager

logger = logging.getLogger(__name__)

# Maximum rows to include in HTML table exports
_MAX_HTML_TABLE_ROWS = 10_000

_STATIC_DIR = Path(__file__).parent / "static"


def export_html(
    study_manager: StudyManager,
    output_path: str | Path,
    study: str | None = None,
) -> Path:
    """Export a study (or all studies) as a self-contained HTML file.

    The exported file includes inlined CSS, vendored JS (Plotly, marked),
    and all artifact data. It opens in any browser without a server.

    Args:
        study_manager: The StudyManager containing study data.
        output_path: Path to write the HTML file.
        study: Specific study label to export, or None for all studies.

    Returns:
        Path to the written file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Gather cards and metadata
    cards = study_manager.list_all_cards(study=study)
    studies = study_manager.list_studies()

    if study:
        studies = [s for s in studies if s["label"] == study]

    # Build the HTML document
    html = _build_html_document(cards, studies, study_manager, study)
    output_path.write_text(html, encoding="utf-8")

    logger.debug(f"Exported HTML: {output_path} ({len(cards)} cards)")
    return output_path


def export_json(
    study_manager: StudyManager,
    output_path: str | Path,
    study: str | None = None,
) -> Path:
    """Export a study (or all studies) as a JSON zip archive.

    The archive contains:
    - meta.json: Export metadata (timestamp, study info)
    - cards.json: All card descriptors
    - artifacts/: Raw artifact files (parquet, json, svg, png)

    Args:
        study_manager: The StudyManager containing study data.
        output_path: Path to write the zip file.
        study: Specific study label to export, or None for all studies.

    Returns:
        Path to the written file.
    """
    output_path = Path(output_path)
    if not str(output_path).endswith(".zip"):
        output_path = output_path.with_suffix(".zip")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cards = study_manager.list_all_cards(study=study)
    studies = study_manager.list_studies()
    if study:
        studies = [s for s in studies if s["label"] == study]

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Export metadata
        meta = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "format_version": "1.0",
            "study": study,
            "studies": studies,
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

            store = study_manager.get_store_for_card(card.card_id)
            if not store:
                continue

            for ext in ("parquet", "json", "svg", "png"):
                artifact_path = store._artifacts_dir / f"{card.artifact_id}.{ext}"
                if artifact_path.exists():
                    arcname = f"artifacts/{card.artifact_id}.{ext}"
                    zf.write(artifact_path, arcname)

        # Output files
        _add_output_files_to_zip(zf, study_manager, study, studies)

    logger.debug(f"Exported JSON zip: {output_path} ({len(cards)} cards)")
    return output_path


def export_html_string(
    study_manager: StudyManager,
    study: str | None = None,
) -> str:
    """Export as HTML and return the string (for server endpoint streaming).

    Args:
        study_manager: The StudyManager containing study data.
        study: Specific study label to export, or None for all studies.

    Returns:
        HTML string.
    """
    cards = study_manager.list_all_cards(study=study)
    studies = study_manager.list_studies()
    if study:
        studies = [s for s in studies if s["label"] == study]
    return _build_html_document(cards, studies, study_manager, study)


def export_json_bytes(
    study_manager: StudyManager,
    study: str | None = None,
) -> bytes:
    """Export as JSON zip and return bytes (for server endpoint streaming).

    Args:
        study_manager: The StudyManager containing study data.
        study: Specific study label to export, or None for all studies.

    Returns:
        Zip file bytes.
    """
    cards = study_manager.list_all_cards(study=study)
    studies = study_manager.list_studies()
    if study:
        studies = [s for s in studies if s["label"] == study]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        meta = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "format_version": "1.0",
            "study": study,
            "studies": studies,
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

            store = study_manager.get_store_for_card(card.card_id)
            if not store:
                continue

            for ext in ("parquet", "json", "svg", "png"):
                artifact_path = store._artifacts_dir / f"{card.artifact_id}.{ext}"
                if artifact_path.exists():
                    arcname = f"artifacts/{card.artifact_id}.{ext}"
                    zf.write(artifact_path, arcname)

        # Output files
        _add_output_files_to_zip(zf, study_manager, study, studies)

    return buf.getvalue()


# --- Output Files in ZIP ---

_MAX_OUTPUT_FILE_SIZE = 50 * 1024 * 1024  # 50MB


def _add_output_files_to_zip(
    zf: zipfile.ZipFile,
    study_manager: StudyManager,
    study: str | None,
    studies: list[dict[str, Any]],
) -> None:
    """Add output directory files to a zip archive.

    Skips files larger than 50MB.
    """
    labels = [study] if study else [s["label"] for s in studies]
    for label in labels:
        output_dir = study_manager.get_output_dir(label)
        if output_dir is None or not output_dir.exists():
            continue

        prefix = f"output/{label}/" if not study else "output/"
        for item in sorted(output_dir.rglob("*")):
            if not item.is_file() or item.name.startswith("."):
                continue
            if item.stat().st_size > _MAX_OUTPUT_FILE_SIZE:
                continue
            rel = str(item.relative_to(output_dir))
            arcname = prefix + rel
            zf.write(item, arcname)


# --- HTML Generation ---


def _build_html_document(
    cards: list[CardDescriptor],
    studies: list[dict[str, Any]],
    study_manager: StudyManager,
    study: str | None,
) -> str:
    """Build a self-contained HTML document with all cards inlined."""
    title = f"M4 Export — {study}" if study else "M4 Export — All Studies"
    export_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Load vendored JS
    plotly_js = _load_vendored_js("plotly.min.js")
    marked_js = _load_vendored_js("marked.min.js")

    # Build card HTML
    cards_html = []
    current_study = None
    for card in cards:
        # Insert study separator if study changed (in "all studies" mode)
        if not study and card.study and card.study != current_study:
            current_study = card.study
            study_meta = _find_study(studies, card.study)
            sep_label = card.study
            if study_meta and study_meta.get("start_time"):
                sep_label += f" &middot; {_format_date(study_meta['start_time'])}"
            cards_html.append(f'<div class="study-separator">{escape(sep_label)}</div>')

        if card.card_type == CardType.SECTION:
            cards_html.append(
                f'<div class="section-divider">{escape(card.title or "")}</div>'
            )
        else:
            cards_html.append(_render_card_html(card, study_manager))

    cards_block = "\n".join(cards_html)

    # Build files section if the study has an output dir
    files_block = ""
    if study:
        files_block = _render_files_section(study, study_manager)
    else:
        # For "all studies" export, render files for each study
        files_parts = []
        for s in studies:
            part = _render_files_section(s["label"], study_manager)
            if part:
                files_parts.append(part)
        files_block = "\n".join(files_parts)

    # Study summary for header
    study_summary = ""
    if study:
        study_meta = _find_study(studies, study)
        if study_meta:
            study_summary = (
                f'<div class="export-study-info">'
                f"<strong>{escape(study)}</strong>"
                f" &middot; {len(cards)} cards"
                f" &middot; {_format_date(study_meta.get('start_time', ''))}"
                f"</div>"
            )
    else:
        study_summary = (
            f'<div class="export-study-info">'
            f"{len(studies)} studies &middot; {len(cards)} cards"
            f"</div>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escape(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=DM+Mono:wght@400;500&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
{_EXPORT_CSS}
{f"<script>{plotly_js}</script>" if plotly_js else ""}
{f"<script>{marked_js}</script>" if marked_js else ""}
</head>
<body>

<div class="export-header">
  <div class="export-header-left">
    <h1>vitrine</h1>
    {study_summary}
  </div>
  <div class="export-header-right">
    <span class="export-timestamp">Exported {export_time}</span>
  </div>
</div>

<div class="feed">
{cards_block if cards_block else '<div class="empty-state">No cards to export</div>'}
</div>

{files_block}

<div class="export-footer">
  vitrine export &middot; {len(cards)} cards &middot; {export_time}
</div>

<script>
{_EXPORT_JS}
</script>
</body>
</html>"""


def _render_card_html(card: CardDescriptor, study_manager: StudyManager) -> str:
    """Render a single card as self-contained HTML."""
    card_type = card.card_type.value
    header_type = (
        "decision" if getattr(card, "response_requested", False) else card_type
    )
    type_letters = {
        "table": "T",
        "markdown": "M",
        "plotly": "P",
        "image": "I",
        "keyvalue": "K",
        "form": "F",
        "section": "S",
        "decision": "!",
    }
    type_letter = type_letters.get(header_type, "?")
    title_text = escape(card.title or card_type)
    desc_html = (
        f'<div class="card-description">{escape(card.description)}</div>'
        if card.description
        else ""
    )
    ts_text = _format_timestamp(card.timestamp) if card.timestamp else ""

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
    body_html = _render_card_body(card, study_manager)

    return f"""<div class="card" data-card-type="{card_type}">
  <div class="card-header" data-type="{header_type}">
    <div class="card-type-icon" data-type="{header_type}">{type_letter}</div>
    <span class="card-title">{title_text}</span>
    <span class="card-meta">{escape(ts_text)}</span>
  </div>
  {desc_html}
  <div class="card-body">{body_html}</div>
  {prov_html}
</div>"""


def _render_card_body(card: CardDescriptor, study_manager: StudyManager) -> str:
    """Render card body content based on card type."""
    if card.card_type == CardType.TABLE:
        return _render_table_html(card, study_manager)
    elif card.card_type == CardType.PLOTLY:
        return _render_plotly_html(card)
    elif card.card_type == CardType.IMAGE:
        return _render_image_html(card)
    elif card.card_type == CardType.MARKDOWN:
        return _render_markdown_html(card)
    elif card.card_type == CardType.KEYVALUE:
        return _render_keyvalue_html(card)
    elif card.card_type == CardType.FORM:
        return _render_form_html(card)
    else:
        return f"<pre>{escape(json.dumps(card.preview, indent=2, default=str))}</pre>"


def _render_table_html(card: CardDescriptor, study_manager: StudyManager) -> str:
    """Render a table card as full HTML table from Parquet artifact."""
    store = study_manager.get_store_for_card(card.card_id)
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


def _render_form_html(card: CardDescriptor) -> str:
    """Render a form card as a frozen key-value summary."""
    fields = card.preview.get("fields", [])
    items = []
    for f in fields:
        label = escape(str(f.get("label") or f.get("name", "")))
        default = f.get("default")
        if default is None:
            val = ""
        elif isinstance(default, bool):
            val = "yes" if default else "no"
        elif isinstance(default, list):
            val = escape(" \u2013 ".join(str(v) for v in default))
        else:
            val = escape(str(default))
        items.append(
            f"<span class='form-frozen-item'>"
            f"<span class='frozen-label'>{label}:</span> "
            f"<span class='frozen-value'>{val}</span></span>"
        )
    return f'<div class="form-frozen">{"".join(items)}</div>'


# --- Files Section for Export ---


def _render_files_section(study_label: str, study_manager: StudyManager) -> str:
    """Render output files as a card-like section for HTML export."""
    output_dir = study_manager.get_output_dir(study_label)
    if output_dir is None or not output_dir.exists():
        return ""

    files = study_manager.list_output_files(study_label)
    # Filter to actual files (not directories)
    files = [f for f in files if not f.get("is_dir")]
    if not files:
        return ""

    _IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg"}
    _TEXT_EXTS = {
        ".py",
        ".sql",
        ".r",
        ".md",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".txt",
        ".cfg",
        ".log",
        ".sh",
        ".ini",
    }
    _TABULAR_EXTS = {".csv", ".parquet"}
    _MAX_INLINE_SIZE = 50 * 1024 * 1024  # 50MB

    items_html = []
    for f in files:
        fpath = study_manager.get_output_file_path(study_label, f["path"])
        if fpath is None:
            continue

        size_str = _format_file_size(f.get("size", 0))
        suffix = fpath.suffix.lower()
        name = escape(f["name"])

        if fpath.stat().st_size > _MAX_INLINE_SIZE:
            items_html.append(
                f'<div class="export-file-entry">'
                f'<div class="export-file-name">{name}'
                f'<span class="export-file-meta">{size_str} (too large to embed)</span>'
                f"</div></div>"
            )
            continue

        if suffix in _IMAGE_EXTS:
            mime = {"svg": "image/svg+xml"}.get(
                suffix.lstrip("."), f"image/{suffix.lstrip('.')}"
            )
            try:
                data_b64 = base64.b64encode(fpath.read_bytes()).decode()
                items_html.append(
                    f'<div class="export-file-entry">'
                    f'<div class="export-file-name">{name}'
                    f'<span class="export-file-meta">{size_str}</span></div>'
                    f'<img src="data:{mime};base64,{data_b64}" '
                    f'alt="{name}" style="max-width:100%;height:auto;margin:8px 0;" />'
                    f"</div>"
                )
            except Exception:
                items_html.append(
                    f'<div class="export-file-entry">'
                    f'<div class="export-file-name">{name}'
                    f'<span class="export-file-meta">{size_str}</span></div>'
                    f"</div>"
                )

        elif suffix in _TEXT_EXTS:
            try:
                text = fpath.read_text(encoding="utf-8", errors="replace")
                items_html.append(
                    f'<div class="export-file-entry">'
                    f'<div class="export-file-name">{name}'
                    f'<span class="export-file-meta">{size_str}</span></div>'
                    f'<pre class="export-file-code">{escape(text)}</pre>'
                    f"</div>"
                )
            except Exception:
                items_html.append(
                    f'<div class="export-file-entry">'
                    f'<div class="export-file-name">{name}'
                    f'<span class="export-file-meta">{size_str}</span></div>'
                    f"</div>"
                )

        elif suffix in _TABULAR_EXTS:
            try:
                con = duckdb.connect(":memory:")
                try:
                    reader = (
                        f"read_csv_auto('{fpath}')"
                        if suffix == ".csv"
                        else f"read_parquet('{fpath}')"
                    )
                    total = con.execute(f"SELECT COUNT(*) FROM {reader}").fetchone()[0]
                    result = con.execute(f"SELECT * FROM {reader} LIMIT 100")
                    columns = [desc[0] for desc in result.description]
                    rows = result.fetchall()
                finally:
                    con.close()

                header = "".join(f"<th>{escape(str(c))}</th>" for c in columns)
                body_rows = []
                for row in rows:
                    cells = "".join(f"<td>{escape(_format_cell(v))}</td>" for v in row)
                    body_rows.append(f"<tr>{cells}</tr>")

                info = f"{total} rows"
                if total > 100:
                    info += " (showing first 100)"

                items_html.append(
                    f'<div class="export-file-entry">'
                    f'<div class="export-file-name">{name}'
                    f'<span class="export-file-meta">{size_str} &middot; {info}</span></div>'
                    f'<div class="table-wrapper">'
                    f"<table><thead><tr>{header}</tr></thead>"
                    f"<tbody>{''.join(body_rows)}</tbody></table></div>"
                    f"</div>"
                )
            except Exception:
                items_html.append(
                    f'<div class="export-file-entry">'
                    f'<div class="export-file-name">{name}'
                    f'<span class="export-file-meta">{size_str}</span></div>'
                    f"</div>"
                )
        else:
            items_html.append(
                f'<div class="export-file-entry">'
                f'<div class="export-file-name">{name}'
                f'<span class="export-file-meta">{size_str}</span></div>'
                f"</div>"
            )

    if not items_html:
        return ""

    return f"""<div class="card" data-card-type="files">
  <div class="card-header" data-type="files" style="background: #f0f1f3;">
    <div class="card-type-icon" data-type="files" style="background: #6b7280; color: #fff;">F</div>
    <span class="card-title">Research Files — {escape(study_label)}</span>
    <span class="card-meta">{len(files)} file{"s" if len(files) != 1 else ""}</span>
  </div>
  <div class="card-body">
    {"".join(items_html)}
  </div>
</div>"""


def _format_file_size(size: int) -> str:
    """Format a file size in bytes to a human-readable string."""
    if size == 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB"]
    i = 0
    s = float(size)
    while s >= 1024 and i < len(units) - 1:
        s /= 1024
        i += 1
    return f"{s:.1f} {units[i]}" if i > 0 else f"{int(s)} {units[i]}"


# --- Helpers ---


def _load_vendored_js(filename: str) -> str:
    """Load a vendored JS file, returning empty string if not found."""
    path = _STATIC_DIR / "vendor" / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _find_study(studies: list[dict[str, Any]], label: str) -> dict[str, Any] | None:
    """Find a study by label in a list of study dicts."""
    for s in studies:
        if s.get("label") == label:
            return s
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
    --bg: #f7f5f0;
    --card-bg: #ffffff;
    --text: #1a1a1a;
    --text-muted: #888888;
    --border: #1a1a1a;
    --border-width: 2px;
    --table-color: #3b82f6;
    --table-bg: #dbeafe;
    --md-color: #8b5cf6;
    --md-bg: #ede9fe;
    --chart-color: #10b981;
    --chart-bg: #d1fae5;
    --kv-color: #f59e0b;
    --kv-bg: #fef3c7;
    --form-color: #ec4899;
    --form-bg: #fce7f3;
    --decision-color: #ef4444;
    --decision-bg: #fee2e2;
    --image-color: #06b6d4;
    --image-bg: #cffafe;
    --shadow: 4px 4px 0 #1a1a1a;
    --shadow-sm: 2px 2px 0 #1a1a1a;
    --font-head: 'Space Grotesk', -apple-system, BlinkMacSystemFont, sans-serif;
    --font-body: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    --font-mono: 'DM Mono', 'SF Mono', Menlo, Consolas, monospace;
    --radius: 0px;
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    font-family: var(--font-body);
    background: var(--bg);
    color: var(--text);
    line-height: 1.5;
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 24px;
  }

  .export-header {
    padding: 20px 0;
    border-bottom: 3px solid var(--border);
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-family: var(--font-head);
  }

  .export-header h1 {
    font-size: 18px;
    font-weight: 700;
  }

  .export-study-info {
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
    background: var(--card-bg);
    border: var(--border-width) solid var(--border);
    border-radius: var(--radius);
    margin-bottom: 16px;
    box-shadow: var(--shadow);
    overflow: hidden;
    page-break-inside: avoid;
  }

  .card-header {
    padding: 10px 14px;
    border-bottom: var(--border-width) solid var(--border);
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .card-header[data-type="table"] { background: var(--table-bg); }
  .card-header[data-type="markdown"] { background: var(--md-bg); }
  .card-header[data-type="plotly"] { background: var(--chart-bg); }
  .card-header[data-type="image"] { background: var(--image-bg); }
  .card-header[data-type="keyvalue"] { background: var(--kv-bg); }
  .card-header[data-type="form"] { background: var(--form-bg); }
  .card-header[data-type="decision"] { background: var(--decision-bg); }

  .card-type-icon {
    width: 28px;
    height: 28px;
    border: var(--border-width) solid var(--border);
    border-radius: var(--radius);
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: var(--font-head);
    font-size: 14px;
    font-weight: 700;
    flex-shrink: 0;
  }

  .card-type-icon[data-type="table"] { background: var(--table-color); color: #fff; }
  .card-type-icon[data-type="markdown"] { background: var(--md-color); color: #fff; }
  .card-type-icon[data-type="plotly"] { background: var(--chart-color); color: #fff; }
  .card-type-icon[data-type="image"] { background: var(--image-color); color: #fff; }
  .card-type-icon[data-type="keyvalue"] { background: var(--kv-color); color: #fff; }
  .card-type-icon[data-type="form"] { background: var(--form-color); color: #fff; }
  .card-type-icon[data-type="decision"] { background: var(--decision-color); color: #fff; }

  .card-title {
    font-family: var(--font-head);
    font-weight: 700;
    font-size: 14px;
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .card-meta {
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--text-muted);
    white-space: nowrap;
  }

  .card-description {
    font-size: 12px;
    color: var(--text-muted);
    padding: 6px 14px 0;
  }

  .card-body {
    padding: 16px;
  }

  .card-provenance {
    padding: 6px 14px;
    font-size: 10px;
    color: var(--text-muted);
    border-top: 1px solid color-mix(in srgb, var(--border) 30%, transparent);
    font-family: var(--font-mono);
  }

  /* Tables */
  .table-info {
    font-size: 12px;
    font-family: var(--font-head);
    color: var(--text-muted);
    padding: 10px 14px;
    border-top: var(--border-width) solid var(--border);
  }

  .table-wrapper {
    overflow-x: auto;
    max-height: 600px;
    overflow-y: auto;
  }

  .table-wrapper table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
    font-family: var(--font-mono);
  }

  .table-wrapper th {
    background: var(--table-bg);
    position: sticky;
    top: 0;
    padding: 8px 14px;
    text-align: left;
    font-family: var(--font-head);
    font-weight: 700;
    border-bottom: var(--border-width) solid var(--border);
    white-space: nowrap;
  }

  .table-wrapper td {
    padding: 6px 14px;
    border-bottom: 1px solid color-mix(in srgb, var(--border) 20%, transparent);
    white-space: nowrap;
    max-width: 300px;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .table-wrapper tr:hover td { background: var(--table-bg); }

  /* Key-Value */
  .kv-table {
    width: auto;
  }

  .kv-key {
    font-family: var(--font-head);
    font-weight: 700;
    padding-right: 24px;
    white-space: nowrap;
    color: var(--text-muted);
    font-size: 12px;
  }

  .kv-value {
    font-family: var(--font-mono);
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
    font-family: var(--font-body);
    font-size: 14px;
    line-height: 1.7;
  }

  .markdown-export h1, .markdown-export h2, .markdown-export h3 {
    margin: 16px 0 8px;
    font-family: var(--font-head);
    font-weight: 700;
  }

  .markdown-export p { margin: 6px 0; }

  .markdown-export pre {
    background: var(--bg);
    border: var(--border-width) solid var(--border);
    box-shadow: var(--shadow-sm);
    padding: 12px 16px;
    overflow-x: auto;
    font-family: var(--font-mono);
    font-size: 12px;
  }

  .markdown-export code {
    font-family: var(--font-mono);
    font-size: 0.9em;
    background: var(--md-bg);
    padding: 1px 4px;
    border: 1px solid color-mix(in srgb, var(--border) 20%, transparent);
  }

  .markdown-export pre code {
    background: none;
    padding: 0;
    border: none;
  }

  /* Section dividers */
  .section-divider {
    font-size: 13px;
    font-family: var(--font-head);
    font-weight: 700;
    color: var(--text);
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 8px 0;
  }

  .section-divider::before,
  .section-divider::after {
    content: '';
    flex: 1;
    height: 3px;
    background: var(--border);
  }

  /* Study separators */
  .study-separator {
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 12px;
    font-family: var(--font-head);
    font-weight: 700;
    color: var(--text-muted);
    padding: 20px 0 8px;
  }

  .study-separator::after {
    content: '';
    flex: 1;
    height: 2px;
    background: var(--border);
  }

  /* Research files section */
  .export-file-entry {
    padding: 8px 0;
    border-bottom: 1px solid color-mix(in srgb, var(--border) 20%, transparent);
  }

  .export-file-entry:last-child {
    border-bottom: none;
  }

  .export-file-name {
    font-family: var(--font-mono);
    font-size: 13px;
    font-weight: 600;
    margin-bottom: 4px;
  }

  .export-file-meta {
    font-weight: 400;
    font-size: 11px;
    color: var(--text-muted);
    margin-left: 8px;
  }

  .export-file-code {
    background: var(--bg);
    border: var(--border-width) solid var(--border);
    box-shadow: var(--shadow-sm);
    padding: 10px 14px;
    overflow-x: auto;
    font-family: var(--font-mono);
    font-size: 11px;
    line-height: 1.5;
    max-height: 400px;
    overflow-y: auto;
    margin: 4px 0;
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
    font-family: var(--font-mono);
    color: var(--text-muted);
    padding: 24px 0;
    border-top: 3px solid var(--border);
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
      border: 1px solid #999;
      margin-bottom: 10px;
      page-break-inside: avoid;
    }

    .card-header {
      border-bottom: 1px solid #999;
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
