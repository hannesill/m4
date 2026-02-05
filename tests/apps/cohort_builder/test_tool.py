"""Tests for cohort builder tool module.

Tests cover:
- Tool protocol fields (name, description, input_model, modalities, supported_datasets)
- is_compatible() returns True for supported datasets, False for others
- QueryCohortTool.invoke() with mock backend returns expected dict structure
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from m4.apps.cohort_builder.query_builder import QueryCohortInput
from m4.apps.cohort_builder.tool import (
    CohortBuilderInput,
    CohortBuilderTool,
    QueryCohortTool,
)
from m4.core.datasets import DatasetDefinition, Modality


class TestCohortBuilderToolProtocol:
    """Test CohortBuilderTool protocol fields."""

    def test_name(self):
        """Tool name should be 'cohort_builder'."""
        tool = CohortBuilderTool()
        assert tool.name == "cohort_builder"

    def test_description(self):
        """Tool should have a description."""
        tool = CohortBuilderTool()
        assert tool.description
        assert "cohort" in tool.description.lower()

    def test_input_model(self):
        """Tool input model should be CohortBuilderInput."""
        tool = CohortBuilderTool()
        assert tool.input_model == CohortBuilderInput

    def test_required_modalities(self):
        """Tool should require TABULAR modality."""
        tool = CohortBuilderTool()
        assert Modality.TABULAR in tool.required_modalities

    def test_supported_datasets(self):
        """Tool should support mimic-iv-demo and mimic-iv."""
        tool = CohortBuilderTool()
        assert "mimic-iv-demo" in tool.supported_datasets
        assert "mimic-iv" in tool.supported_datasets


class TestQueryCohortToolProtocol:
    """Test QueryCohortTool protocol fields."""

    def test_name(self):
        """Tool name should be 'query_cohort'."""
        tool = QueryCohortTool()
        assert tool.name == "query_cohort"

    def test_description(self):
        """Tool should have a description."""
        tool = QueryCohortTool()
        assert tool.description
        assert "cohort" in tool.description.lower()

    def test_input_model(self):
        """Tool input model should be QueryCohortInput."""
        tool = QueryCohortTool()
        assert tool.input_model == QueryCohortInput

    def test_required_modalities(self):
        """Tool should require TABULAR modality."""
        tool = QueryCohortTool()
        assert Modality.TABULAR in tool.required_modalities

    def test_supported_datasets(self):
        """Tool should support mimic-iv-demo and mimic-iv."""
        tool = QueryCohortTool()
        assert "mimic-iv-demo" in tool.supported_datasets
        assert "mimic-iv" in tool.supported_datasets


class TestCohortBuilderToolCompatibility:
    """Test CohortBuilderTool.is_compatible()."""

    def test_compatible_with_mimic_iv_demo(self):
        """Tool should be compatible with mimic-iv-demo."""
        tool = CohortBuilderTool()
        dataset = DatasetDefinition(
            name="mimic-iv-demo",
            modalities=frozenset({Modality.TABULAR}),
        )
        assert tool.is_compatible(dataset)

    def test_compatible_with_mimic_iv(self):
        """Tool should be compatible with mimic-iv."""
        tool = CohortBuilderTool()
        dataset = DatasetDefinition(
            name="mimic-iv",
            modalities=frozenset({Modality.TABULAR}),
        )
        assert tool.is_compatible(dataset)

    def test_incompatible_with_eicu(self):
        """Tool should not be compatible with eicu."""
        tool = CohortBuilderTool()
        dataset = DatasetDefinition(
            name="eicu",
            modalities=frozenset({Modality.TABULAR}),
        )
        assert not tool.is_compatible(dataset)

    def test_incompatible_without_tabular(self):
        """Tool should not be compatible without TABULAR modality."""
        tool = CohortBuilderTool()
        dataset = DatasetDefinition(
            name="mimic-iv-demo",
            modalities=frozenset({Modality.NOTES}),
        )
        assert not tool.is_compatible(dataset)


class TestQueryCohortToolCompatibility:
    """Test QueryCohortTool.is_compatible()."""

    def test_compatible_with_mimic_iv_demo(self):
        """Tool should be compatible with mimic-iv-demo."""
        tool = QueryCohortTool()
        dataset = DatasetDefinition(
            name="mimic-iv-demo",
            modalities=frozenset({Modality.TABULAR}),
        )
        assert tool.is_compatible(dataset)

    def test_incompatible_with_eicu(self):
        """Tool should not be compatible with eicu."""
        tool = QueryCohortTool()
        dataset = DatasetDefinition(
            name="eicu",
            modalities=frozenset({Modality.TABULAR}),
        )
        assert not tool.is_compatible(dataset)


class TestCohortBuilderToolInvoke:
    """Test CohortBuilderTool.invoke()."""

    def test_invoke_returns_dict(self):
        """invoke() should return a dict with expected keys."""
        tool = CohortBuilderTool()
        dataset = DatasetDefinition(
            name="mimic-iv-demo",
            modalities=frozenset({Modality.TABULAR}),
        )
        params = CohortBuilderInput()

        result = tool.invoke(dataset, params)

        assert isinstance(result, dict)
        assert "message" in result
        assert "dataset" in result
        assert "supported_criteria" in result

    def test_invoke_includes_dataset_name(self):
        """invoke() result should include the dataset name."""
        tool = CohortBuilderTool()
        dataset = DatasetDefinition(
            name="mimic-iv-demo",
            modalities=frozenset({Modality.TABULAR}),
        )

        result = tool.invoke(dataset, CohortBuilderInput())

        assert result["dataset"] == "mimic-iv-demo"

    def test_invoke_includes_all_supported_criteria(self):
        """invoke() result should list all supported criteria."""
        tool = CohortBuilderTool()
        dataset = DatasetDefinition(
            name="mimic-iv",
            modalities=frozenset({Modality.TABULAR}),
        )

        result = tool.invoke(dataset, CohortBuilderInput())

        criteria = result["supported_criteria"]
        assert "age_min" in criteria
        assert "age_max" in criteria
        assert "gender" in criteria
        assert "icd_codes" in criteria
        assert "has_icu_stay" in criteria
        assert "in_hospital_mortality" in criteria


class TestQueryCohortToolInvoke:
    """Test QueryCohortTool.invoke() with mock backend."""

    @pytest.fixture
    def mock_backend(self):
        """Create a mock backend that returns test data."""
        backend = MagicMock()

        # Mock count query result
        count_df = pd.DataFrame({"patient_count": [100], "admission_count": [150]})
        count_result = MagicMock()
        count_result.success = True
        count_result.dataframe = count_df

        # Mock demographics query result
        demographics_df = pd.DataFrame(
            {
                "age_bucket": ["20-29", "30-39", "40-49"],
                "patient_count": [20, 35, 45],
            }
        )
        demographics_result = MagicMock()
        demographics_result.success = True
        demographics_result.dataframe = demographics_df

        # Mock gender query result
        gender_df = pd.DataFrame({"gender": ["F", "M"], "patient_count": [55, 45]})
        gender_result = MagicMock()
        gender_result.success = True
        gender_result.dataframe = gender_df

        # Return different results based on query
        def execute_query(sql, dataset):
            if "age_bucket" in sql:
                return demographics_result
            elif "GROUP BY p.gender" in sql:
                return gender_result
            else:
                return count_result

        backend.execute_query.side_effect = execute_query
        return backend

    def test_invoke_returns_expected_structure(self, mock_backend):
        """invoke() should return dict with expected structure."""
        tool = QueryCohortTool()
        dataset = DatasetDefinition(
            name="mimic-iv-demo",
            modalities=frozenset({Modality.TABULAR}),
        )
        params = QueryCohortInput()

        with patch(
            "m4.apps.cohort_builder.tool.get_backend", return_value=mock_backend
        ):
            result = tool.invoke(dataset, params)

        assert "patient_count" in result
        assert "admission_count" in result
        assert "demographics" in result
        assert "criteria" in result
        assert "sql" in result

    def test_invoke_returns_counts(self, mock_backend):
        """invoke() should return correct counts from mock."""
        tool = QueryCohortTool()
        dataset = DatasetDefinition(
            name="mimic-iv-demo",
            modalities=frozenset({Modality.TABULAR}),
        )
        params = QueryCohortInput()

        with patch(
            "m4.apps.cohort_builder.tool.get_backend", return_value=mock_backend
        ):
            result = tool.invoke(dataset, params)

        assert result["patient_count"] == 100
        assert result["admission_count"] == 150

    def test_invoke_returns_demographics(self, mock_backend):
        """invoke() should return demographics from mock."""
        tool = QueryCohortTool()
        dataset = DatasetDefinition(
            name="mimic-iv-demo",
            modalities=frozenset({Modality.TABULAR}),
        )
        params = QueryCohortInput()

        with patch(
            "m4.apps.cohort_builder.tool.get_backend", return_value=mock_backend
        ):
            result = tool.invoke(dataset, params)

        assert "age" in result["demographics"]
        assert "gender" in result["demographics"]
        assert result["demographics"]["age"]["20-29"] == 20
        assert result["demographics"]["gender"]["F"] == 55

    def test_invoke_returns_criteria(self, mock_backend):
        """invoke() should echo back the criteria in result."""
        tool = QueryCohortTool()
        dataset = DatasetDefinition(
            name="mimic-iv-demo",
            modalities=frozenset({Modality.TABULAR}),
        )
        params = QueryCohortInput(
            age_min=18,
            age_max=65,
            gender="M",
            icd_codes=["I10"],
            has_icu_stay=True,
            in_hospital_mortality=False,
        )

        with patch(
            "m4.apps.cohort_builder.tool.get_backend", return_value=mock_backend
        ):
            result = tool.invoke(dataset, params)

        criteria = result["criteria"]
        assert criteria["age_min"] == 18
        assert criteria["age_max"] == 65
        assert criteria["gender"] == "M"
        assert criteria["icd_codes"] == ["I10"]
        assert criteria["has_icu_stay"] is True
        assert criteria["in_hospital_mortality"] is False

    def test_invoke_returns_sql(self, mock_backend):
        """invoke() should include generated SQL."""
        tool = QueryCohortTool()
        dataset = DatasetDefinition(
            name="mimic-iv-demo",
            modalities=frozenset({Modality.TABULAR}),
        )
        params = QueryCohortInput(age_min=18)

        with patch(
            "m4.apps.cohort_builder.tool.get_backend", return_value=mock_backend
        ):
            result = tool.invoke(dataset, params)

        sql = result["sql"]
        assert "SELECT" in sql
        assert "FROM" in sql
        assert "p.anchor_age >= 18" in sql

    def test_invoke_validates_criteria(self, mock_backend):
        """invoke() should raise ValueError for invalid criteria."""
        tool = QueryCohortTool()
        dataset = DatasetDefinition(
            name="mimic-iv-demo",
            modalities=frozenset({Modality.TABULAR}),
        )
        params = QueryCohortInput(age_min=-1)

        with patch(
            "m4.apps.cohort_builder.tool.get_backend", return_value=mock_backend
        ):
            with pytest.raises(ValueError, match="age_min must be between"):
                tool.invoke(dataset, params)


class TestQueryCohortToolEdgeCases:
    """Test QueryCohortTool edge case handling (Phase 4 hardening)."""

    def test_invoke_handles_empty_dataframe(self):
        """invoke() should return 0 counts when database is empty."""
        tool = QueryCohortTool()
        dataset = DatasetDefinition(
            name="mimic-iv-demo",
            modalities=frozenset({Modality.TABULAR}),
        )
        params = QueryCohortInput()

        # Create mock backend with empty dataframes
        backend = MagicMock()

        empty_count_result = MagicMock()
        empty_count_result.success = True
        empty_count_result.dataframe = pd.DataFrame()  # Empty

        empty_demo_result = MagicMock()
        empty_demo_result.success = True
        empty_demo_result.dataframe = pd.DataFrame()  # Empty

        empty_gender_result = MagicMock()
        empty_gender_result.success = True
        empty_gender_result.dataframe = pd.DataFrame()  # Empty

        def execute_query(sql, dataset):
            if "age_bucket" in sql:
                return empty_demo_result
            elif "GROUP BY p.gender" in sql:
                return empty_gender_result
            else:
                return empty_count_result

        backend.execute_query.side_effect = execute_query

        with patch("m4.apps.cohort_builder.tool.get_backend", return_value=backend):
            result = tool.invoke(dataset, params)

        # Should return 0 counts, not crash
        assert result["patient_count"] == 0
        assert result["admission_count"] == 0
        assert result["demographics"]["age"] == {}
        assert result["demographics"]["gender"] == {}

    def test_invoke_handles_none_dataframe(self):
        """invoke() should return 0 counts when dataframe is None."""
        tool = QueryCohortTool()
        dataset = DatasetDefinition(
            name="mimic-iv-demo",
            modalities=frozenset({Modality.TABULAR}),
        )
        params = QueryCohortInput()

        # Create mock backend with None dataframes
        backend = MagicMock()

        none_result = MagicMock()
        none_result.success = True
        none_result.dataframe = None  # None instead of empty

        backend.execute_query.return_value = none_result

        with patch("m4.apps.cohort_builder.tool.get_backend", return_value=backend):
            result = tool.invoke(dataset, params)

        assert result["patient_count"] == 0
        assert result["admission_count"] == 0
        assert result["demographics"]["age"] == {}
        assert result["demographics"]["gender"] == {}

    def test_invoke_handles_null_values_in_cells(self):
        """invoke() should handle None values in dataframe cells gracefully."""
        tool = QueryCohortTool()
        dataset = DatasetDefinition(
            name="mimic-iv-demo",
            modalities=frozenset({Modality.TABULAR}),
        )
        params = QueryCohortInput()

        backend = MagicMock()

        # Count with None values in cells
        count_df = pd.DataFrame({"patient_count": [None], "admission_count": [None]})
        count_result = MagicMock()
        count_result.success = True
        count_result.dataframe = count_df

        # Demographics with mixed None values
        demographics_df = pd.DataFrame(
            {
                "age_bucket": ["20-29", None, "40-49"],
                "patient_count": [20, 30, None],
            }
        )
        demo_result = MagicMock()
        demo_result.success = True
        demo_result.dataframe = demographics_df

        # Gender with None values
        gender_df = pd.DataFrame({"gender": ["F", None], "patient_count": [55, None]})
        gender_result = MagicMock()
        gender_result.success = True
        gender_result.dataframe = gender_df

        def execute_query(sql, dataset):
            if "age_bucket" in sql:
                return demo_result
            elif "GROUP BY p.gender" in sql:
                return gender_result
            else:
                return count_result

        backend.execute_query.side_effect = execute_query

        with patch("m4.apps.cohort_builder.tool.get_backend", return_value=backend):
            result = tool.invoke(dataset, params)

        # Count should be 0 for None values
        assert result["patient_count"] == 0
        assert result["admission_count"] == 0
        # Only valid rows should be included
        assert result["demographics"]["age"] == {"20-29": 20}
        assert result["demographics"]["gender"] == {"F": 55}

    def test_invoke_handles_icu_with_empty_database(self):
        """invoke() should return 0 ICU stay count when database is empty."""
        tool = QueryCohortTool()
        dataset = DatasetDefinition(
            name="mimic-iv-demo",
            modalities=frozenset({Modality.TABULAR}),
        )
        params = QueryCohortInput(has_icu_stay=True)

        backend = MagicMock()

        # Empty count result with ICU column
        count_df = pd.DataFrame(
            {
                "patient_count": [0],
                "admission_count": [0],
                "icu_stay_count": [0],
            }
        )
        count_result = MagicMock()
        count_result.success = True
        count_result.dataframe = count_df

        empty_result = MagicMock()
        empty_result.success = True
        empty_result.dataframe = pd.DataFrame()

        def execute_query(sql, dataset):
            if "age_bucket" in sql:
                return empty_result
            elif "GROUP BY p.gender" in sql:
                return empty_result
            else:
                return count_result

        backend.execute_query.side_effect = execute_query

        with patch("m4.apps.cohort_builder.tool.get_backend", return_value=backend):
            result = tool.invoke(dataset, params)

        assert result["patient_count"] == 0
        assert result["admission_count"] == 0
        assert result["icu_stay_count"] == 0
