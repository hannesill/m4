"""Tests for the first-class M4Client API."""

import json
import os
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from m4 import M4Client
from m4.core.backends.base import QueryResult
from m4.core.datasets import DatasetDefinition, Modality
from m4.core.exceptions import ModalityError
from m4.core.tools import init_tools


@pytest.fixture(autouse=True)
def initialized_tools():
    init_tools()


@pytest.fixture
def tabular_dataset():
    return DatasetDefinition(
        name="test-tabular",
        modalities=frozenset({Modality.TABULAR}),
    )


@pytest.fixture
def notes_dataset():
    return DatasetDefinition(
        name="test-notes",
        modalities=frozenset({Modality.NOTES}),
    )


@pytest.fixture
def backend():
    mock = MagicMock()
    mock.name = "mock"
    mock.get_backend_info.return_value = "Mock backend"
    return mock


def test_constructor_resolves_dataset_and_backend(tabular_dataset, backend):
    client = M4Client(dataset=tabular_dataset, backend=backend, interface="python_api")

    assert client.dataset is tabular_dataset
    assert client.backend is backend
    assert client.context.backend_name == "mock"
    assert client.context.interface == "python_api"


def test_schema_table_info_and_query_delegate_through_context(tabular_dataset, backend):
    schema_df = pd.DataFrame({"name": ["subject_id"], "type": ["INTEGER"]})
    sample_df = pd.DataFrame({"subject_id": [1]})
    query_df = pd.DataFrame({"count": [1]})

    backend.get_table_list.return_value = ["patients"]
    backend.get_table_info.return_value = QueryResult(dataframe=schema_df, row_count=1)
    backend.get_sample_data.return_value = QueryResult(dataframe=sample_df, row_count=1)
    backend.execute_query.return_value = QueryResult(dataframe=query_df, row_count=1)

    client = M4Client(dataset=tabular_dataset, backend=backend)

    assert client.schema()["tables"] == ["patients"]
    assert client.table_info("patients")["schema"].equals(schema_df)
    assert client.query("SELECT COUNT(*) FROM patients").equals(query_df)

    backend.get_table_list.assert_called_once_with(tabular_dataset, client.context)
    backend.get_table_info.assert_called_once_with(
        "patients", tabular_dataset, client.context
    )
    backend.execute_query.assert_called_once_with(
        "SELECT COUNT(*) FROM patients", tabular_dataset, client.context
    )


def test_explicit_backend_selection_does_not_mutate_environment(tabular_dataset):
    previous = os.environ.get("M4_BACKEND")
    os.environ["M4_BACKEND"] = "duckdb"

    try:
        with patch("m4.client.get_backend") as mock_get_backend:
            mock_backend = MagicMock()
            mock_backend.name = "bigquery"
            mock_backend.get_table_list.return_value = []
            mock_backend.get_backend_info.return_value = "BigQuery"
            mock_get_backend.return_value = mock_backend

            client = M4Client(dataset=tabular_dataset, backend="bigquery")
            client.schema()

        assert client.context.backend_name == "bigquery"
        assert os.environ.get("M4_BACKEND") == "duckdb"
        mock_get_backend.assert_called_once_with("bigquery")
    finally:
        if previous is None:
            os.environ.pop("M4_BACKEND", None)
        else:
            os.environ["M4_BACKEND"] = previous


def test_explicit_attribution_recorded_without_environment(tabular_dataset, backend):
    os.environ.pop("M4_STUDY_ID", None)
    os.environ.pop("M4_SESSION_ID", None)
    os.environ.pop("M4_ACTOR", None)

    backend.execute_query.return_value = QueryResult(
        dataframe=pd.DataFrame({"x": [1]}), row_count=1
    )
    client = M4Client(
        dataset=tabular_dataset,
        backend=backend,
        study_id="study-1",
        session_id="session-1",
        actor="actor-1",
    )

    with patch("m4.core.telemetry.logger") as mock_logger:
        client.query("SELECT 1")

    record = json.loads(mock_logger.info.call_args[0][0])
    assert record["interface"] == "python_api"
    assert record["study_id"] == "study-1"
    assert record["session_id"] == "session-1"
    assert record["actor"] == "actor-1"


def test_notes_methods_raise_for_tabular_dataset(tabular_dataset, backend):
    client = M4Client(dataset=tabular_dataset, backend=backend)

    with pytest.raises(ModalityError):
        client.search_notes("pneumonia")
