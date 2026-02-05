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
