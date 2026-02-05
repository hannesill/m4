"""MCP integration tests for cohort builder.

Tests cover:
- cohort_builder tool through fastmcp.Client
- query_cohort tool through fastmcp.Client with test DuckDB
- _meta.ui.resourceUri is present in tool listing
"""

import json
import os
from unittest.mock import patch

import pytest
from fastmcp import Client

from m4.core.datasets import DatasetDefinition, Modality
from m4.core.tools import init_tools
from m4.mcp_server import mcp


def extract_json_from_result(result) -> dict:
    """Extract JSON data from a CallToolResult.

    The result structure has a content attribute with text content.
    """
    # Try to access content attribute
    content = getattr(result, "content", None)
    if content is None:
        # Try direct access
        content = result

    # Find text content
    if isinstance(content, list):
        for item in content:
            if hasattr(item, "text"):
                return json.loads(item.text)
            if isinstance(item, dict) and "text" in item:
                return json.loads(item["text"])

    # Try direct text attribute
    if hasattr(content, "text"):
        return json.loads(content.text)

    raise ValueError(f"Could not extract JSON from result: {result}")


@pytest.fixture(autouse=True)
def ensure_tools_initialized():
    """Ensure tools are initialized before each test."""
    init_tools()


@pytest.fixture
def cohort_test_db(tmp_path):
    """Create a test DuckDB database with cohort-related tables.

    Tables:
    - mimiciv_hosp.patients: subject_id, gender, anchor_age
    - mimiciv_hosp.admissions: subject_id, hadm_id, hospital_expire_flag
    - mimiciv_hosp.diagnoses_icd: hadm_id, icd_code
    - mimiciv_icu.icustays: subject_id, hadm_id, stay_id
    """
    import duckdb

    db_path = tmp_path / "cohort_test.duckdb"
    con = duckdb.connect(str(db_path))
    try:
        # Create schemas
        con.execute("CREATE SCHEMA mimiciv_hosp")
        con.execute("CREATE SCHEMA mimiciv_icu")

        # Create patients table
        con.execute(
            """
            CREATE TABLE mimiciv_hosp.patients (
                subject_id INTEGER PRIMARY KEY,
                gender VARCHAR(1),
                anchor_age INTEGER
            )
            """
        )
        con.execute(
            """
            INSERT INTO mimiciv_hosp.patients (subject_id, gender, anchor_age) VALUES
                (1, 'M', 45),
                (2, 'F', 62),
                (3, 'M', 28),
                (4, 'F', 75),
                (5, 'M', 55)
            """
        )

        # Create admissions table
        con.execute(
            """
            CREATE TABLE mimiciv_hosp.admissions (
                hadm_id INTEGER PRIMARY KEY,
                subject_id INTEGER,
                hospital_expire_flag INTEGER
            )
            """
        )
        con.execute(
            """
            INSERT INTO mimiciv_hosp.admissions (hadm_id, subject_id, hospital_expire_flag) VALUES
                (101, 1, 0),
                (102, 2, 0),
                (103, 3, 1),
                (104, 4, 0),
                (105, 5, 1)
            """
        )

        # Create diagnoses_icd table
        con.execute(
            """
            CREATE TABLE mimiciv_hosp.diagnoses_icd (
                hadm_id INTEGER,
                icd_code VARCHAR(10)
            )
            """
        )
        con.execute(
            """
            INSERT INTO mimiciv_hosp.diagnoses_icd (hadm_id, icd_code) VALUES
                (101, 'I10'),
                (101, 'E11.9'),
                (102, 'I10'),
                (103, 'J18.9'),
                (104, 'E11.9'),
                (105, 'I10')
            """
        )

        # Create icustays table
        con.execute(
            """
            CREATE TABLE mimiciv_icu.icustays (
                stay_id INTEGER PRIMARY KEY,
                subject_id INTEGER,
                hadm_id INTEGER
            )
            """
        )
        con.execute(
            """
            INSERT INTO mimiciv_icu.icustays (stay_id, subject_id, hadm_id) VALUES
                (1001, 1, 101),
                (1002, 3, 103),
                (1003, 5, 105)
            """
        )

        con.commit()
    finally:
        con.close()

    return str(db_path)


class TestCohortBuilderMCPIntegration:
    """Test cohort_builder tool through MCP client."""

    async def test_cohort_builder_tool_exists(self, cohort_test_db):
        """cohort_builder tool should be available."""
        from m4.core.backends import reset_backend_cache

        reset_backend_cache()

        with patch.dict(
            os.environ,
            {
                "M4_BACKEND": "duckdb",
                "M4_DB_PATH": cohort_test_db,
                "M4_OAUTH2_ENABLED": "false",
            },
            clear=True,
        ):
            async with Client(mcp) as client:
                tools = await client.list_tools()
                tool_names = [t.name for t in tools]

                assert "cohort_builder" in tool_names

    async def test_cohort_builder_returns_message(self, cohort_test_db):
        """cohort_builder tool should return welcome message."""
        from m4.core.backends import reset_backend_cache

        reset_backend_cache()

        mock_ds = DatasetDefinition(
            name="mimic-iv-demo",
            modalities=frozenset({Modality.TABULAR}),
        )

        with patch.dict(
            os.environ,
            {
                "M4_BACKEND": "duckdb",
                "M4_DB_PATH": cohort_test_db,
                "M4_OAUTH2_ENABLED": "false",
            },
            clear=True,
        ):
            with patch(
                "m4.mcp_server.DatasetRegistry.get_active", return_value=mock_ds
            ):
                async with Client(mcp) as client:
                    result = await client.call_tool("cohort_builder", {})
                    result_text = str(result)

                    assert (
                        "Cohort Builder" in result_text
                        or "cohort" in result_text.lower()
                    )

    async def test_meta_ui_resource_uri_present(self, cohort_test_db):
        """cohort_builder tool should have _meta.ui.resourceUri."""
        from m4.core.backends import reset_backend_cache

        reset_backend_cache()

        with patch.dict(
            os.environ,
            {
                "M4_BACKEND": "duckdb",
                "M4_DB_PATH": cohort_test_db,
                "M4_OAUTH2_ENABLED": "false",
            },
            clear=True,
        ):
            async with Client(mcp) as client:
                tools = await client.list_tools()

                # Find the cohort_builder tool
                cohort_tool = next(
                    (t for t in tools if t.name == "cohort_builder"), None
                )
                assert cohort_tool is not None

                # Check for _meta.ui.resourceUri
                # The _meta field might be accessed differently depending on MCP version
                meta = getattr(cohort_tool, "meta", None)
                if meta is None:
                    # Try alternative access
                    tool_dict = cohort_tool.model_dump(by_alias=True)
                    meta = tool_dict.get("_meta", {})

                assert meta is not None
                assert "ui" in meta
                assert "resourceUri" in meta["ui"]
                assert "cohort-builder" in meta["ui"]["resourceUri"]


class TestQueryCohortMCPIntegration:
    """Test query_cohort tool through MCP client."""

    async def test_query_cohort_tool_exists(self, cohort_test_db):
        """query_cohort tool should be available."""
        from m4.core.backends import reset_backend_cache

        reset_backend_cache()

        with patch.dict(
            os.environ,
            {
                "M4_BACKEND": "duckdb",
                "M4_DB_PATH": cohort_test_db,
                "M4_OAUTH2_ENABLED": "false",
            },
            clear=True,
        ):
            async with Client(mcp) as client:
                tools = await client.list_tools()
                tool_names = [t.name for t in tools]

                assert "query_cohort" in tool_names

    async def test_query_cohort_empty_criteria(self, cohort_test_db):
        """query_cohort with empty criteria should return all patients."""
        from m4.core.backends import reset_backend_cache

        reset_backend_cache()

        mock_ds = DatasetDefinition(
            name="mimic-iv-demo",
            modalities=frozenset({Modality.TABULAR}),
        )

        with patch.dict(
            os.environ,
            {
                "M4_BACKEND": "duckdb",
                "M4_DB_PATH": cohort_test_db,
                "M4_OAUTH2_ENABLED": "false",
            },
            clear=True,
        ):
            with patch(
                "m4.mcp_server.DatasetRegistry.get_active", return_value=mock_ds
            ):
                with patch("m4.apps.cohort_builder.tool.get_backend") as mock_backend:
                    from m4.core.backends.duckdb import DuckDBBackend

                    mock_backend.return_value = DuckDBBackend(
                        db_path_override=cohort_test_db
                    )

                    async with Client(mcp) as client:
                        result = await client.call_tool("query_cohort", {})
                        result_text = str(result)

                        # Should have patient count
                        assert "patient_count" in result_text
                        # We have 5 patients in our test DB
                        assert "5" in result_text

    async def test_query_cohort_with_age_filter(self, cohort_test_db):
        """query_cohort with age filter should return filtered patients."""
        from m4.core.backends import reset_backend_cache

        reset_backend_cache()

        mock_ds = DatasetDefinition(
            name="mimic-iv-demo",
            modalities=frozenset({Modality.TABULAR}),
        )

        with patch.dict(
            os.environ,
            {
                "M4_BACKEND": "duckdb",
                "M4_DB_PATH": cohort_test_db,
                "M4_OAUTH2_ENABLED": "false",
            },
            clear=True,
        ):
            with patch(
                "m4.mcp_server.DatasetRegistry.get_active", return_value=mock_ds
            ):
                with patch("m4.apps.cohort_builder.tool.get_backend") as mock_backend:
                    from m4.core.backends.duckdb import DuckDBBackend

                    mock_backend.return_value = DuckDBBackend(
                        db_path_override=cohort_test_db
                    )

                    async with Client(mcp) as client:
                        # Filter for patients >= 50 years old
                        result = await client.call_tool("query_cohort", {"age_min": 50})

                        # Should return JSON with patient count
                        # Patients >= 50: 2 (62yo), 4 (75yo), 5 (55yo) = 3 patients
                        data = extract_json_from_result(result)
                        assert data["patient_count"] == 3

    async def test_query_cohort_with_gender_filter(self, cohort_test_db):
        """query_cohort with gender filter should return filtered patients."""
        from m4.core.backends import reset_backend_cache

        reset_backend_cache()

        mock_ds = DatasetDefinition(
            name="mimic-iv-demo",
            modalities=frozenset({Modality.TABULAR}),
        )

        with patch.dict(
            os.environ,
            {
                "M4_BACKEND": "duckdb",
                "M4_DB_PATH": cohort_test_db,
                "M4_OAUTH2_ENABLED": "false",
            },
            clear=True,
        ):
            with patch(
                "m4.mcp_server.DatasetRegistry.get_active", return_value=mock_ds
            ):
                with patch("m4.apps.cohort_builder.tool.get_backend") as mock_backend:
                    from m4.core.backends.duckdb import DuckDBBackend

                    mock_backend.return_value = DuckDBBackend(
                        db_path_override=cohort_test_db
                    )

                    async with Client(mcp) as client:
                        # Filter for female patients
                        result = await client.call_tool("query_cohort", {"gender": "F"})
                        data = extract_json_from_result(result)

                        # Female patients: 2, 4 = 2 patients
                        assert data["patient_count"] == 2

    async def test_query_cohort_with_icd_filter(self, cohort_test_db):
        """query_cohort with ICD code filter should return filtered patients."""
        from m4.core.backends import reset_backend_cache

        reset_backend_cache()

        mock_ds = DatasetDefinition(
            name="mimic-iv-demo",
            modalities=frozenset({Modality.TABULAR}),
        )

        with patch.dict(
            os.environ,
            {
                "M4_BACKEND": "duckdb",
                "M4_DB_PATH": cohort_test_db,
                "M4_OAUTH2_ENABLED": "false",
            },
            clear=True,
        ):
            with patch(
                "m4.mcp_server.DatasetRegistry.get_active", return_value=mock_ds
            ):
                with patch("m4.apps.cohort_builder.tool.get_backend") as mock_backend:
                    from m4.core.backends.duckdb import DuckDBBackend

                    mock_backend.return_value = DuckDBBackend(
                        db_path_override=cohort_test_db
                    )

                    async with Client(mcp) as client:
                        # Filter for patients with I10 (hypertension)
                        result = await client.call_tool(
                            "query_cohort", {"icd_codes": ["I10"]}
                        )
                        data = extract_json_from_result(result)

                        # Patients with I10: 1, 2, 5 = 3 patients
                        assert data["patient_count"] == 3

    async def test_query_cohort_with_icu_filter(self, cohort_test_db):
        """query_cohort with ICU stay filter should return filtered patients."""
        from m4.core.backends import reset_backend_cache

        reset_backend_cache()

        mock_ds = DatasetDefinition(
            name="mimic-iv-demo",
            modalities=frozenset({Modality.TABULAR}),
        )

        with patch.dict(
            os.environ,
            {
                "M4_BACKEND": "duckdb",
                "M4_DB_PATH": cohort_test_db,
                "M4_OAUTH2_ENABLED": "false",
            },
            clear=True,
        ):
            with patch(
                "m4.mcp_server.DatasetRegistry.get_active", return_value=mock_ds
            ):
                with patch("m4.apps.cohort_builder.tool.get_backend") as mock_backend:
                    from m4.core.backends.duckdb import DuckDBBackend

                    mock_backend.return_value = DuckDBBackend(
                        db_path_override=cohort_test_db
                    )

                    async with Client(mcp) as client:
                        # Filter for ICU patients only
                        result = await client.call_tool(
                            "query_cohort", {"has_icu_stay": True}
                        )
                        data = extract_json_from_result(result)

                        # ICU patients: 1, 3, 5 = 3 patients
                        assert data["patient_count"] == 3

                        # Filter for non-ICU patients
                        result = await client.call_tool(
                            "query_cohort", {"has_icu_stay": False}
                        )
                        data = extract_json_from_result(result)

                        # Non-ICU patients: 2, 4 = 2 patients
                        assert data["patient_count"] == 2

    async def test_query_cohort_with_mortality_filter(self, cohort_test_db):
        """query_cohort with mortality filter should return filtered patients."""
        from m4.core.backends import reset_backend_cache

        reset_backend_cache()

        mock_ds = DatasetDefinition(
            name="mimic-iv-demo",
            modalities=frozenset({Modality.TABULAR}),
        )

        with patch.dict(
            os.environ,
            {
                "M4_BACKEND": "duckdb",
                "M4_DB_PATH": cohort_test_db,
                "M4_OAUTH2_ENABLED": "false",
            },
            clear=True,
        ):
            with patch(
                "m4.mcp_server.DatasetRegistry.get_active", return_value=mock_ds
            ):
                with patch("m4.apps.cohort_builder.tool.get_backend") as mock_backend:
                    from m4.core.backends.duckdb import DuckDBBackend

                    mock_backend.return_value = DuckDBBackend(
                        db_path_override=cohort_test_db
                    )

                    async with Client(mcp) as client:
                        # Filter for deceased patients
                        result = await client.call_tool(
                            "query_cohort", {"in_hospital_mortality": True}
                        )
                        data = extract_json_from_result(result)

                        # Deceased patients: 3, 5 = 2 patients
                        assert data["patient_count"] == 2

    async def test_query_cohort_combined_filters(self, cohort_test_db):
        """query_cohort with combined filters should return correct patients."""
        from m4.core.backends import reset_backend_cache

        reset_backend_cache()

        mock_ds = DatasetDefinition(
            name="mimic-iv-demo",
            modalities=frozenset({Modality.TABULAR}),
        )

        with patch.dict(
            os.environ,
            {
                "M4_BACKEND": "duckdb",
                "M4_DB_PATH": cohort_test_db,
                "M4_OAUTH2_ENABLED": "false",
            },
            clear=True,
        ):
            with patch(
                "m4.mcp_server.DatasetRegistry.get_active", return_value=mock_ds
            ):
                with patch("m4.apps.cohort_builder.tool.get_backend") as mock_backend:
                    from m4.core.backends.duckdb import DuckDBBackend

                    mock_backend.return_value = DuckDBBackend(
                        db_path_override=cohort_test_db
                    )

                    async with Client(mcp) as client:
                        # Male + ICU + I10
                        result = await client.call_tool(
                            "query_cohort",
                            {
                                "gender": "M",
                                "has_icu_stay": True,
                                "icd_codes": ["I10"],
                            },
                        )
                        data = extract_json_from_result(result)

                        # Male ICU patients with I10: 1, 5 = 2 patients
                        assert data["patient_count"] == 2


class TestCohortBuilderResource:
    """Test cohort builder UI resource."""

    async def test_resource_exists(self, cohort_test_db):
        """Cohort builder UI resource should be available."""
        from m4.core.backends import reset_backend_cache

        reset_backend_cache()

        with patch.dict(
            os.environ,
            {
                "M4_BACKEND": "duckdb",
                "M4_DB_PATH": cohort_test_db,
                "M4_OAUTH2_ENABLED": "false",
            },
            clear=True,
        ):
            async with Client(mcp) as client:
                resources = await client.list_resources()
                resource_uris = [r.uri for r in resources]

                # Should have the cohort builder UI resource
                assert any("cohort-builder" in str(uri) for uri in resource_uris)

    async def test_resource_returns_html(self, cohort_test_db):
        """Cohort builder resource should return HTML content."""
        from m4.apps.cohort_builder import get_ui_html

        html = get_ui_html()

        assert "<html" in html.lower()
        assert "M4 Cohort Builder" in html
        # Should have the SDK bundled
        assert "App" in html or "@modelcontextprotocol" in html
