"""M4 Display: Visualization backend for code execution agents.

Provides a local display server that pushes visualizations to a browser tab.
Agents call show() to render DataFrames, charts, markdown, and more.

Quick Start:
    from m4.display import show

    show(df, title="Demographics")
    show("## Key Finding\\nMortality is 23%")
"""
