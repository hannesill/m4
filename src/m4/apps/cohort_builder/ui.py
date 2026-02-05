"""UI resource serving for the Cohort Builder MCP App.

This module provides the HTML bundle that hosts render in an iframe when
the cohort_builder tool is called. The HTML is a single-file bundle built
with Vite that includes the MCP Apps SDK for host communication.
"""

from pathlib import Path

# MCP Apps resource URI - used in _meta.ui.resourceUri
RESOURCE_URI = "ui://m4/cohort-builder"

# Path to the built HTML bundle (output from Vite build)
_UI_HTML_PATH = Path(__file__).parent / "mcp-app.html"


def get_ui_html() -> str:
    """Get the cohort builder UI HTML bundle.

    Returns:
        The complete HTML string ready to be served as an MCP resource

    Raises:
        FileNotFoundError: If ui.html hasn't been built yet
    """
    if not _UI_HTML_PATH.exists():
        raise FileNotFoundError(
            f"UI bundle not found at {_UI_HTML_PATH}. "
            "Run 'cd src/m4/apps/cohort_builder/ui && npm install && npm run build' first."
        )

    return _UI_HTML_PATH.read_text(encoding="utf-8")
