"""Derived table support for M4.

Built-in derived tables are clinically validated, read-only concept tables
materialized from vendored mimic-code SQL. They provide pre-computed clinical
concepts (SOFA scores, sepsis cohorts, KDIGO staging, etc.) that are
immediately queryable via standard SQL.
"""

from m4.core.derived.materializer import materialize_all

__all__ = ["materialize_all"]
