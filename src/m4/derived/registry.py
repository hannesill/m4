"""Registry for MIMIC-IV derived tables.

Derived tables are based on MIT-LCP mimic-code:
https://github.com/MIT-LCP/mimic-code/tree/main/mimic-iv/concepts

WARNING: This module is for internal CLI use only.
The registry is read-only and cannot be modified at runtime.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar


@dataclass(frozen=True)
class DerivedTableDefinition:
    """Definition of a derived table (immutable)."""

    name: str
    sql_file: str
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    description: str = ""
    applicable_datasets: tuple[str, ...] = field(
        default_factory=lambda: ("mimic-iv", "mimic-iv-demo")
    )


# Hardcoded table definitions - cannot be modified at runtime
# Source: MIT-LCP mimic-code (BigQuery → DuckDB converted)
_DERIVED_TABLES: tuple[DerivedTableDefinition, ...] = (
    DerivedTableDefinition(
        name="age",
        sql_file="age.sql",
        dependencies=(),
        description="Patient age at hospital admission",
    ),
    DerivedTableDefinition(
        name="gcs",
        sql_file="gcs.sql",
        dependencies=(),
        description="Glasgow Coma Scale measurements",
    ),
    DerivedTableDefinition(
        name="vitalsign",
        sql_file="vitalsign.sql",
        dependencies=(),
        description="Vital sign measurements (HR, BP, RR, Temp, SpO2, Glucose)",
    ),
    DerivedTableDefinition(
        name="urine_output",
        sql_file="urine_output.sql",
        dependencies=(),
        description="Urine output measurements",
    ),
    DerivedTableDefinition(
        name="ventilator_setting",
        sql_file="ventilator_setting.sql",
        dependencies=(),
        description="Ventilator settings and modes",
    ),
    DerivedTableDefinition(
        name="oxygen_delivery",
        sql_file="oxygen_delivery.sql",
        dependencies=(),
        description="Oxygen delivery devices and flow rates",
    ),
    DerivedTableDefinition(
        name="first_day_gcs",
        sql_file="first_day_gcs.sql",
        dependencies=("gcs",),
        description="First day GCS (minimum in first 24h of ICU stay)",
    ),
    DerivedTableDefinition(
        name="first_day_vitalsign",
        sql_file="first_day_vitalsign.sql",
        dependencies=("vitalsign",),
        description="First day vital signs (min/max/mean in first 24h of ICU stay)",
    ),
    DerivedTableDefinition(
        name="first_day_urine_output",
        sql_file="first_day_urine_output.sql",
        dependencies=("urine_output",),
        description="First day urine output (total in first 24h of ICU stay)",
    ),
    DerivedTableDefinition(
        name="ventilation",
        sql_file="ventilation.sql",
        dependencies=("ventilator_setting", "oxygen_delivery"),
        description="Ventilation status classification",
    ),
)


class DerivedTableRegistry:
    """Read-only registry for derived table definitions.

    This registry cannot be modified at runtime. All table definitions
    are hardcoded to prevent unauthorized table creation.
    """

    _tables: ClassVar[dict[str, DerivedTableDefinition]] = {
        t.name: t for t in _DERIVED_TABLES
    }

    @classmethod
    def get(cls, name: str) -> DerivedTableDefinition | None:
        """Get a derived table definition by name."""
        return cls._tables.get(name)

    @classmethod
    def get_all(cls) -> list[DerivedTableDefinition]:
        """Get all registered derived tables."""
        return list(cls._tables.values())

    @classmethod
    def get_tables_for_dataset(cls, dataset_name: str) -> list[DerivedTableDefinition]:
        """Get derived tables applicable to a specific dataset."""
        return [
            t
            for t in cls._tables.values()
            if dataset_name.lower() in [d.lower() for d in t.applicable_datasets]
        ]

    @classmethod
    def get_execution_order(
        cls, tables: list[DerivedTableDefinition] | None = None
    ) -> list[DerivedTableDefinition]:
        """Get tables in topologically sorted order based on dependencies.

        Args:
            tables: List of tables to sort. If None, uses all registered tables.

        Returns:
            List of tables in execution order (dependencies first).

        Raises:
            ValueError: If circular dependencies are detected.
        """
        if tables is None:
            tables = cls.get_all()

        table_map = {t.name: t for t in tables}
        visited: set[str] = set()
        visiting: set[str] = set()
        result: list[DerivedTableDefinition] = []

        def visit(name: str) -> None:
            if name in visited:
                return
            if name in visiting:
                raise ValueError(f"Circular dependency detected involving '{name}'")

            visiting.add(name)
            table = table_map.get(name)
            if table:
                for dep in table.dependencies:
                    if dep in table_map:
                        visit(dep)
                visited.add(name)
                visiting.remove(name)
                result.append(table)

        for table in tables:
            visit(table.name)

        return result

    @classmethod
    def get_scripts_dir(cls) -> Path:
        """Get the directory containing SQL scripts."""
        return Path(__file__).parent / "scripts"
