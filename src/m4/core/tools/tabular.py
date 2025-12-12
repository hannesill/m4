"""Tabular data tools for querying structured medical databases.

This module provides capability-based tools for querying tabular medical data
such as ICU stays, lab results, and demographic statistics.

All tools use the Backend protocol directly - no circular dependencies.
"""

from dataclasses import dataclass

from m4.core.backends import get_backend
from m4.core.datasets import Capability, DatasetDefinition, Modality
from m4.core.tools.base import ToolInput, ToolOutput
from m4.core.validation import (
    format_error_with_guidance,
    is_safe_query,
    validate_limit,
)


# Input/Output models for specific tools
@dataclass
class GetDatabaseSchemaInput(ToolInput):
    """Input for get_database_schema tool."""

    pass  # No parameters needed


@dataclass
class GetTableInfoInput(ToolInput):
    """Input for get_table_info tool."""

    table_name: str
    show_sample: bool = True


@dataclass
class ExecuteQueryInput(ToolInput):
    """Input for execute_query tool."""

    sql_query: str


@dataclass
class GetICUStaysInput(ToolInput):
    """Input for get_icu_stays tool."""

    patient_id: int | None = None
    limit: int = 10


@dataclass
class GetLabResultsInput(ToolInput):
    """Input for get_lab_results tool."""

    patient_id: int | None = None
    limit: int = 20


@dataclass
class GetRaceDistributionInput(ToolInput):
    """Input for get_race_distribution tool."""

    limit: int = 10


# Tool implementations
class GetDatabaseSchemaTool:
    """Tool for listing available tables in the database.

    This tool provides schema introspection capabilities, showing all
    available tables and their relationships. Works with any dataset
    that has tabular data.
    """

    name = "get_database_schema"
    description = "📚 List all available tables in the database"
    input_model = GetDatabaseSchemaInput
    output_model = ToolOutput

    # Compatibility constraints
    required_modalities: frozenset[Modality] = frozenset({Modality.TABULAR})
    required_capabilities: frozenset[Capability] = frozenset(
        {Capability.SCHEMA_INTROSPECTION}
    )
    supported_datasets: frozenset[str] | None = None

    def invoke(
        self, dataset: DatasetDefinition, params: GetDatabaseSchemaInput
    ) -> ToolOutput:
        """List available tables using the backend."""
        backend = get_backend()
        backend_info = backend.get_backend_info(dataset)

        try:
            tables = backend.get_table_list(dataset)
            if not tables:
                return ToolOutput(
                    result=f"{backend_info}\n📋 **Available Tables:**\nNo tables found"
                )

            table_list = "\n".join(f"  {t}" for t in tables)
            return ToolOutput(
                result=f"{backend_info}\n📋 **Available Tables:**\n{table_list}"
            )
        except Exception as e:
            return ToolOutput(result=f"{backend_info}\n❌ Error: {e}")

    def is_compatible(self, dataset: DatasetDefinition) -> bool:
        """Check if this tool is compatible with the given dataset."""
        if self.supported_datasets and dataset.name not in self.supported_datasets:
            return False
        if not self.required_modalities.issubset(dataset.modalities):
            return False
        if not self.required_capabilities.issubset(dataset.capabilities):
            return False
        return True


class GetTableInfoTool:
    """Tool for inspecting table structure and sample data.

    Shows column names, data types, and optionally sample rows for a
    specified table.
    """

    name = "get_table_info"
    description = "🔍 Get detailed information about a specific table"
    input_model = GetTableInfoInput
    output_model = ToolOutput

    required_modalities: frozenset[Modality] = frozenset({Modality.TABULAR})
    required_capabilities: frozenset[Capability] = frozenset(
        {Capability.SCHEMA_INTROSPECTION}
    )
    supported_datasets: frozenset[str] | None = None

    def invoke(
        self, dataset: DatasetDefinition, params: GetTableInfoInput
    ) -> ToolOutput:
        """Get table structure and sample data using the backend."""
        backend = get_backend()
        backend_info = backend.get_backend_info(dataset)

        try:
            # Get table schema
            schema_result = backend.get_table_info(params.table_name, dataset)
            if not schema_result.success:
                return ToolOutput(result=f"{backend_info}\n❌ {schema_result.error}")

            result_parts = [
                backend_info,
                f"📋 **Table:** {params.table_name}",
                "",
                "**Column Information:**",
                schema_result.data,
            ]

            # Get sample data if requested
            if params.show_sample:
                sample_result = backend.get_sample_data(
                    params.table_name, dataset, limit=3
                )
                if sample_result.success:
                    result_parts.extend(
                        [
                            "",
                            "📊 **Sample Data (first 3 rows):**",
                            sample_result.data,
                        ]
                    )

            return ToolOutput(result="\n".join(result_parts))
        except Exception as e:
            return ToolOutput(
                result=f"{backend_info}\n❌ Error examining table '{params.table_name}': {e}"
            )

    def is_compatible(self, dataset: DatasetDefinition) -> bool:
        """Check compatibility."""
        if self.supported_datasets and dataset.name not in self.supported_datasets:
            return False
        if not self.required_modalities.issubset(dataset.modalities):
            return False
        if not self.required_capabilities.issubset(dataset.capabilities):
            return False
        return True


class ExecuteQueryTool:
    """Tool for executing SQL queries on the dataset.

    Allows running SELECT queries with built-in safety validation
    to prevent SQL injection and unauthorized operations.
    """

    name = "execute_query"
    description = "🚀 Execute SQL queries to analyze data"
    input_model = ExecuteQueryInput
    output_model = ToolOutput

    required_modalities: frozenset[Modality] = frozenset({Modality.TABULAR})
    required_capabilities: frozenset[Capability] = frozenset({Capability.COHORT_QUERY})
    supported_datasets: frozenset[str] | None = None

    def invoke(
        self, dataset: DatasetDefinition, params: ExecuteQueryInput
    ) -> ToolOutput:
        """Execute a SQL query with safety validation."""
        # Validate query first
        safe, msg = is_safe_query(params.sql_query)
        if not safe:
            return ToolOutput(result=f"❌ **Security Error:** {msg}")

        backend = get_backend()

        try:
            result = backend.execute_query(params.sql_query, dataset)
            if result.success:
                return ToolOutput(result=result.data)
            else:
                return ToolOutput(
                    result=format_error_with_guidance(result.error or "Unknown error")
                )
        except Exception as e:
            return ToolOutput(result=format_error_with_guidance(str(e)))

    def is_compatible(self, dataset: DatasetDefinition) -> bool:
        """Check compatibility."""
        if self.supported_datasets and dataset.name not in self.supported_datasets:
            return False
        if not self.required_modalities.issubset(dataset.modalities):
            return False
        if not self.required_capabilities.issubset(dataset.capabilities):
            return False
        return True


class GetICUStaysTool:
    """Tool for retrieving ICU stay information.

    Convenience tool that uses dataset table_mappings for table names.
    """

    name = "get_icu_stays"
    description = "🏥 Get ICU stay information and length of stay data"
    input_model = GetICUStaysInput
    output_model = ToolOutput

    required_modalities: frozenset[Modality] = frozenset({Modality.TABULAR})
    required_capabilities: frozenset[Capability] = frozenset({Capability.ICU_STAYS})
    supported_datasets: frozenset[str] | None = None

    def invoke(
        self, dataset: DatasetDefinition, params: GetICUStaysInput
    ) -> ToolOutput:
        """Get ICU stays using table_mappings for table name resolution."""
        if not validate_limit(params.limit):
            return ToolOutput(
                result="Error: Invalid limit. Must be between 1 and 1000."
            )

        backend = get_backend()

        # Use table_mappings for table name resolution
        table_name = dataset.table_mappings.get("icustays", "icustays")

        # Build query
        if params.patient_id:
            query = f"SELECT * FROM {table_name} WHERE subject_id = {params.patient_id}"
        else:
            query = f"SELECT * FROM {table_name} LIMIT {params.limit}"

        try:
            result = backend.execute_query(query, dataset)
            if result.success:
                return ToolOutput(result=result.data)
            else:
                return ToolOutput(
                    result=self._format_convenience_error(
                        result.error or "Query failed"
                    )
                )
        except Exception as e:
            return ToolOutput(result=self._format_convenience_error(str(e)))

    def _format_convenience_error(self, error: str) -> str:
        """Format error with guidance for convenience tool failures."""
        return f"""❌ **Convenience function failed:** {error}

💡 **For reliable results, use the proper workflow:**
1. `get_database_schema()` ← See actual table names
2. `get_table_info('table_name')` ← Understand structure
3. `execute_query('your_sql')` ← Use exact names

This ensures compatibility across different dataset setups."""

    def is_compatible(self, dataset: DatasetDefinition) -> bool:
        """Check compatibility."""
        if self.supported_datasets and dataset.name not in self.supported_datasets:
            return False
        if not self.required_modalities.issubset(dataset.modalities):
            return False
        if not self.required_capabilities.issubset(dataset.capabilities):
            return False
        return True


class GetLabResultsTool:
    """Tool for retrieving laboratory test results.

    Convenience tool that uses dataset table_mappings for table names.
    """

    name = "get_lab_results"
    description = "🧪 Get laboratory test results and values"
    input_model = GetLabResultsInput
    output_model = ToolOutput

    required_modalities: frozenset[Modality] = frozenset({Modality.TABULAR})
    required_capabilities: frozenset[Capability] = frozenset({Capability.LAB_RESULTS})
    supported_datasets: frozenset[str] | None = None

    def invoke(
        self, dataset: DatasetDefinition, params: GetLabResultsInput
    ) -> ToolOutput:
        """Get lab results using table_mappings for table name resolution."""
        if not validate_limit(params.limit):
            return ToolOutput(
                result="Error: Invalid limit. Must be between 1 and 1000."
            )

        backend = get_backend()

        # Use table_mappings for table name resolution
        table_name = dataset.table_mappings.get("labevents", "labevents")

        # Build query
        if params.patient_id:
            query = (
                f"SELECT * FROM {table_name} "
                f"WHERE subject_id = {params.patient_id} LIMIT {params.limit}"
            )
        else:
            query = f"SELECT * FROM {table_name} LIMIT {params.limit}"

        try:
            result = backend.execute_query(query, dataset)
            if result.success:
                return ToolOutput(result=result.data)
            else:
                return ToolOutput(
                    result=self._format_convenience_error(
                        result.error or "Query failed"
                    )
                )
        except Exception as e:
            return ToolOutput(result=self._format_convenience_error(str(e)))

    def _format_convenience_error(self, error: str) -> str:
        """Format error with guidance for convenience tool failures."""
        return f"""❌ **Convenience function failed:** {error}

💡 **For reliable results, use the proper workflow:**
1. `get_database_schema()` ← See actual table names
2. `get_table_info('table_name')` ← Understand structure
3. `execute_query('your_sql')` ← Use exact names

This ensures compatibility across different dataset setups."""

    def is_compatible(self, dataset: DatasetDefinition) -> bool:
        """Check compatibility."""
        if self.supported_datasets and dataset.name not in self.supported_datasets:
            return False
        if not self.required_modalities.issubset(dataset.modalities):
            return False
        if not self.required_capabilities.issubset(dataset.capabilities):
            return False
        return True


class GetRaceDistributionTool:
    """Tool for analyzing demographic statistics.

    Provides aggregate statistics on patient demographics, particularly
    racial/ethnic distribution in the dataset.
    """

    name = "get_race_distribution"
    description = "📊 Get patient demographic distribution statistics"
    input_model = GetRaceDistributionInput
    output_model = ToolOutput

    required_modalities: frozenset[Modality] = frozenset({Modality.TABULAR})
    required_capabilities: frozenset[Capability] = frozenset(
        {Capability.DEMOGRAPHIC_STATS}
    )
    supported_datasets: frozenset[str] | None = None

    def invoke(
        self, dataset: DatasetDefinition, params: GetRaceDistributionInput
    ) -> ToolOutput:
        """Get race distribution using table_mappings for table name resolution."""
        if not validate_limit(params.limit):
            return ToolOutput(
                result="Error: Invalid limit. Must be between 1 and 1000."
            )

        backend = get_backend()

        # Use table_mappings for table name resolution
        table_name = dataset.table_mappings.get("admissions", "admissions")

        # Build query
        query = (
            f"SELECT race, COUNT(*) as count FROM {table_name} "
            f"GROUP BY race ORDER BY count DESC LIMIT {params.limit}"
        )

        try:
            result = backend.execute_query(query, dataset)
            if result.success:
                return ToolOutput(result=result.data)
            else:
                return ToolOutput(
                    result=self._format_convenience_error(
                        result.error or "Query failed"
                    )
                )
        except Exception as e:
            return ToolOutput(result=self._format_convenience_error(str(e)))

    def _format_convenience_error(self, error: str) -> str:
        """Format error with guidance for convenience tool failures."""
        return f"""❌ **Convenience function failed:** {error}

💡 **For reliable results, use the proper workflow:**
1. `get_database_schema()` ← See actual table names
2. `get_table_info('table_name')` ← Understand structure
3. `execute_query('your_sql')` ← Use exact names

This ensures compatibility across different dataset setups."""

    def is_compatible(self, dataset: DatasetDefinition) -> bool:
        """Check compatibility."""
        if self.supported_datasets and dataset.name not in self.supported_datasets:
            return False
        if not self.required_modalities.issubset(dataset.modalities):
            return False
        if not self.required_capabilities.issubset(dataset.capabilities):
            return False
        return True
