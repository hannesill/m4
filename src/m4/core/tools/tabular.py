"""Tabular data tools for querying structured medical databases.

This module provides capability-based tools for querying tabular medical data
such as ICU stays, lab results, and demographic statistics.
"""

from dataclasses import dataclass

from m4.core.datasets import Capability, DatasetDefinition, Modality
from m4.core.tools.base import ToolInput, ToolOutput


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
    limit: int = 10


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
    supported_datasets: frozenset[str] | None = None  # Works with any tabular dataset

    def invoke(
        self, dataset: DatasetDefinition, params: GetDatabaseSchemaInput
    ) -> ToolOutput:
        """Execute the tool.

        This is a placeholder that will be connected to the actual
        backend implementation in mcp_server.py during Phase 2.

        Args:
            dataset: The dataset to query
            params: Tool input parameters

        Returns:
            ToolOutput with schema information
        """
        # Import here to avoid circular dependency
        from m4 import mcp_server

        result = mcp_server._get_database_schema_internal()
        return ToolOutput(result=result)

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
        """Execute the tool."""
        from m4 import mcp_server

        result = mcp_server._get_table_info_internal(
            params.table_name, params.show_sample
        )
        return ToolOutput(result=result)

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

    name = "execute_mimic_query"
    description = "🚀 Execute SQL queries to analyze medical data"
    input_model = ExecuteQueryInput
    output_model = ToolOutput

    required_modalities: frozenset[Modality] = frozenset({Modality.TABULAR})
    required_capabilities: frozenset[Capability] = frozenset({Capability.COHORT_QUERY})
    supported_datasets: frozenset[str] | None = None

    def invoke(
        self, dataset: DatasetDefinition, params: ExecuteQueryInput
    ) -> ToolOutput:
        """Execute the tool."""
        from m4 import mcp_server

        result = mcp_server._execute_query_internal(params.sql_query)
        return ToolOutput(result=result)

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

    Convenience tool that assumes standard MIMIC-IV table structure.
    For best results, use the schema exploration workflow first.
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
        """Execute the tool."""
        from m4 import mcp_server

        result = mcp_server._get_icu_stays_internal(params.patient_id, params.limit)
        return ToolOutput(result=result)

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

    Convenience tool for common lab queries. Assumes MIMIC-IV structure.
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
        """Execute the tool."""
        from m4 import mcp_server

        result = mcp_server._get_lab_results_internal(params.patient_id, params.limit)
        return ToolOutput(result=result)

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
        """Execute the tool."""
        from m4 import mcp_server

        result = mcp_server._get_race_distribution_internal(params.limit)
        return ToolOutput(result=result)

    def is_compatible(self, dataset: DatasetDefinition) -> bool:
        """Check compatibility."""
        if self.supported_datasets and dataset.name not in self.supported_datasets:
            return False
        if not self.required_modalities.issubset(dataset.modalities):
            return False
        if not self.required_capabilities.issubset(dataset.capabilities):
            return False
        return True
