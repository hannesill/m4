"""Cohort Builder tool implementations.

This module provides two tools:
- CohortBuilderTool: Entry point that triggers UI rendering in MCP Apps hosts
- QueryCohortTool: Backend tool called by UI for live cohort queries
"""

from dataclasses import dataclass
from typing import Any

from m4.apps.cohort_builder.query_builder import (
    QueryCohortInput,
    build_cohort_count_sql,
    build_cohort_demographics_sql,
    build_gender_distribution_sql,
)
from m4.core.backends import get_backend
from m4.core.datasets import DatasetDefinition, Modality
from m4.core.exceptions import QueryError, SecurityError
from m4.core.tools.base import ToolInput
from m4.core.validation import is_safe_query


@dataclass
class CohortBuilderInput(ToolInput):
    """Input for cohort_builder tool.

    The cohort_builder tool takes no parameters - it simply launches the UI.
    All filtering is done interactively through the UI.
    """

    pass


class CohortBuilderTool:
    """Entry point tool for the cohort builder MCP App.

    When called by an LLM, this tool returns dataset information as text
    (for non-UI hosts) and triggers the UI rendering in hosts that support
    MCP Apps.

    The UI itself calls QueryCohortTool for live updates as users refine
    their cohort criteria.
    """

    name = "cohort_builder"
    description = (
        "Launch the interactive cohort builder UI. "
        "Filter patients by age, gender, and other criteria with live counts. "
        "Requires a host that supports MCP Apps (like Claude Desktop)."
    )
    input_model = CohortBuilderInput

    required_modalities: frozenset[Modality] = frozenset({Modality.TABULAR})
    supported_datasets: frozenset[str] | None = frozenset({"mimic-iv-demo", "mimic-iv"})

    def invoke(
        self, dataset: DatasetDefinition, params: CohortBuilderInput
    ) -> dict[str, Any]:
        """Launch the cohort builder.

        Returns dataset info for text-only hosts. The actual UI rendering
        is handled by the MCP Apps protocol via _meta.ui.resourceUri.

        Args:
            dataset: The active dataset
            params: Tool parameters (empty for this tool)

        Returns:
            Dict with dataset info and welcome message
        """
        return {
            "message": (
                f"Cohort Builder ready for {dataset.name}. "
                "Use the interactive UI to filter patients by criteria."
            ),
            "dataset": dataset.name,
            "supported_criteria": [
                "age_min",
                "age_max",
                "gender",
                "icd_codes",
                "icd_match_all",
                "has_icu_stay",
                "in_hospital_mortality",
            ],
        }

    def is_compatible(self, dataset: DatasetDefinition) -> bool:
        """Check if this tool is compatible with the given dataset."""
        if self.supported_datasets is not None:
            if dataset.name not in self.supported_datasets:
                return False

        if not self.required_modalities.issubset(dataset.modalities):
            return False

        return True


class QueryCohortTool:
    """Backend tool for cohort queries.

    Called by the cohort builder UI to get live counts as users adjust
    filtering criteria. Returns patient counts, admission counts, and
    demographic distributions.
    """

    name = "query_cohort"
    description = (
        "Query cohort counts and demographics based on filtering criteria. "
        "Used by the cohort builder UI for live updates."
    )
    input_model = QueryCohortInput

    required_modalities: frozenset[Modality] = frozenset({Modality.TABULAR})
    supported_datasets: frozenset[str] | None = frozenset({"mimic-iv-demo", "mimic-iv"})

    def invoke(
        self, dataset: DatasetDefinition, params: QueryCohortInput
    ) -> dict[str, Any]:
        """Execute cohort query and return results.

        Args:
            dataset: The active dataset
            params: Cohort filtering criteria

        Returns:
            Dict with patient_count, admission_count, demographics, and sql

        Raises:
            SecurityError: If generated SQL fails validation
            QueryError: If query execution fails
        """
        # Build SQL queries
        count_sql = build_cohort_count_sql(params)
        demographics_sql = build_cohort_demographics_sql(params)
        gender_sql = build_gender_distribution_sql(params)

        # Validate all queries
        for sql, name in [
            (count_sql, "count"),
            (demographics_sql, "demographics"),
            (gender_sql, "gender"),
        ]:
            safe, msg = is_safe_query(sql)
            if not safe:
                raise SecurityError(
                    f"Generated {name} query failed validation: {msg}",
                    query=sql,
                )

        # Execute queries
        backend = get_backend()

        count_result = backend.execute_query(count_sql, dataset)
        if not count_result.success:
            raise QueryError(
                count_result.error or "Count query failed",
                sql=count_sql,
            )

        demographics_result = backend.execute_query(demographics_sql, dataset)
        if not demographics_result.success:
            raise QueryError(
                demographics_result.error or "Demographics query failed",
                sql=demographics_sql,
            )

        gender_result = backend.execute_query(gender_sql, dataset)
        if not gender_result.success:
            raise QueryError(
                gender_result.error or "Gender query failed",
                sql=gender_sql,
            )

        # Extract results
        count_df = count_result.dataframe
        patient_count = (
            int(count_df["patient_count"].iloc[0]) if count_df is not None else 0
        )
        admission_count = (
            int(count_df["admission_count"].iloc[0]) if count_df is not None else 0
        )

        # Build age distribution dict
        age_distribution = {}
        if demographics_result.dataframe is not None:
            for _, row in demographics_result.dataframe.iterrows():
                age_distribution[row["age_bucket"]] = int(row["patient_count"])

        # Build gender distribution dict
        gender_distribution = {}
        if gender_result.dataframe is not None:
            for _, row in gender_result.dataframe.iterrows():
                gender_distribution[row["gender"]] = int(row["patient_count"])

        return {
            "patient_count": patient_count,
            "admission_count": admission_count,
            "demographics": {
                "age": age_distribution,
                "gender": gender_distribution,
            },
            "criteria": {
                "age_min": params.age_min,
                "age_max": params.age_max,
                "gender": params.gender,
                "icd_codes": params.icd_codes,
                "icd_match_all": params.icd_match_all,
                "has_icu_stay": params.has_icu_stay,
                "in_hospital_mortality": params.in_hospital_mortality,
            },
            "sql": count_sql,
        }

    def is_compatible(self, dataset: DatasetDefinition) -> bool:
        """Check if this tool is compatible with the given dataset."""
        if self.supported_datasets is not None:
            if dataset.name not in self.supported_datasets:
                return False

        if not self.required_modalities.issubset(dataset.modalities):
            return False

        return True
