"""Cohort Builder MCP App.

An interactive cohort builder that renders a UI in hosts supporting MCP Apps.
Users can filter patients by criteria and see live counts as they refine.

Components:
    - CohortBuilderTool: Entry point tool that triggers UI rendering
    - QueryCohortTool: Backend tool called by UI for live cohort queries
    - query_builder: SQL generation for cohort criteria
    - ui: HTML resource serving
"""

from m4.apps.cohort_builder.query_builder import (
    QueryCohortInput,
    build_cohort_count_sql,
    build_cohort_demographics_sql,
)
from m4.apps.cohort_builder.tool import (
    CohortBuilderInput,
    CohortBuilderTool,
    QueryCohortTool,
)
from m4.apps.cohort_builder.ui import RESOURCE_URI, get_ui_html

__all__ = [
    "RESOURCE_URI",
    "CohortBuilderInput",
    "CohortBuilderTool",
    "QueryCohortInput",
    "QueryCohortTool",
    "build_cohort_count_sql",
    "build_cohort_demographics_sql",
    "get_ui_html",
]
