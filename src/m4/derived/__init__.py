"""Derived table management for MIMIC-IV datasets.

This module provides internal functionality to create and manage derived tables
based on MIT-LCP mimic-code definitions.

WARNING: This module is for internal CLI use only. Do not expose these classes
to external interfaces (MCP tools, etc.) as they can modify the database.
"""

# Internal imports only - not exposed in __all__
# Use: from m4.derived.registry import DerivedTableRegistry
# Only from trusted internal code (cli.py, data_io.py)

__all__: list[str] = []  # Nothing is publicly exported
