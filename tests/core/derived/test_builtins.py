"""Tests for m4.core.derived.builtins module.

Tests cover:
- Execution order parsing from duckdb.sql orchestrator
- Builtin table listing
- Error handling for unsupported datasets
- SQL file integrity checks
"""

from pathlib import Path

import pytest

from m4.core.derived.builtins import (
    _BUILTINS_DIR,
    get_execution_order,
    get_tables_by_category,
    has_derived_support,
    list_builtins,
)


class TestGetExecutionOrder:
    """Tests for get_execution_order()."""

    def test_returns_list_of_paths_for_mimic_iv(self):
        result = get_execution_order("mimic-iv")
        assert isinstance(result, list)
        assert len(result) > 0
        assert all(isinstance(p, Path) for p in result)

    def test_all_paths_exist(self):
        result = get_execution_order("mimic-iv")
        for path in result:
            assert path.exists(), f"SQL file does not exist: {path}"

    def test_all_paths_are_sql_files(self):
        result = get_execution_order("mimic-iv")
        for path in result:
            assert path.suffix == ".sql", f"Not a SQL file: {path}"

    def test_returns_expected_count(self):
        """Should have ~63 SQL files based on the mimic-code orchestrator."""
        result = get_execution_order("mimic-iv")
        assert len(result) >= 50, f"Expected at least 50 SQL files, got {len(result)}"

    def test_dependencies_come_first(self):
        """Key dependency tables should appear before their dependents."""
        result = get_execution_order("mimic-iv")
        names = [p.stem for p in result]

        # icustay_times is a dependency that should come early
        assert "icustay_times" in names

        # sofa depends on icustay_hourly, which depends on icustay_times
        assert names.index("icustay_times") < names.index("icustay_hourly")
        assert names.index("icustay_hourly") < names.index("sofa")

        # sepsis3 depends on sofa and suspicion_of_infection
        assert names.index("sofa") < names.index("sepsis3")
        assert names.index("suspicion_of_infection") < names.index("sepsis3")

        # kdigo_stages depends on kdigo_uo and kdigo_creatinine
        assert names.index("kdigo_uo") < names.index("kdigo_stages")
        assert names.index("kdigo_creatinine") < names.index("kdigo_stages")

    def test_key_tables_present(self):
        """Important clinical concept tables should be included."""
        names = [p.stem for p in get_execution_order("mimic-iv")]
        expected = [
            "age",
            "sofa",
            "sepsis3",
            "charlson",
            "kdigo_stages",
            "sapsii",
            "apsiii",
            "oasis",
            "lods",
            "sirs",
            "ventilation",
            "crrt",
            "rrt",
            "suspicion_of_infection",
            "norepinephrine_equivalent_dose",
        ]
        for table in expected:
            assert table in names, f"Expected table '{table}' not in execution order"

    def test_unsupported_dataset_raises_value_error(self):
        with pytest.raises(ValueError, match="No built-in derived tables"):
            get_execution_order("eicu")

    def test_unknown_dataset_raises_value_error(self):
        with pytest.raises(ValueError, match="No built-in derived tables"):
            get_execution_order("nonexistent-dataset")

    def test_paths_are_within_builtins_dir(self):
        result = get_execution_order("mimic-iv")
        for path in result:
            assert str(path).startswith(str(_BUILTINS_DIR)), (
                f"Path {path} is outside builtins directory"
            )


class TestListBuiltins:
    """Tests for list_builtins()."""

    def test_returns_list_of_strings(self):
        result = list_builtins("mimic-iv")
        assert isinstance(result, list)
        assert all(isinstance(name, str) for name in result)

    def test_returns_table_names_not_paths(self):
        result = list_builtins("mimic-iv")
        for name in result:
            assert "/" not in name, f"Name should not contain path separator: {name}"
            assert "." not in name, f"Name should not contain extension: {name}"

    def test_matches_execution_order_count(self):
        order = get_execution_order("mimic-iv")
        names = list_builtins("mimic-iv")
        assert len(names) == len(order)

    def test_matches_execution_order_names(self):
        order = get_execution_order("mimic-iv")
        names = list_builtins("mimic-iv")
        expected = [p.stem for p in order]
        assert names == expected

    def test_unsupported_dataset_raises_value_error(self):
        with pytest.raises(ValueError, match="No built-in derived tables"):
            list_builtins("eicu")

    def test_contains_key_clinical_concepts(self):
        names = list_builtins("mimic-iv")
        assert "sofa" in names
        assert "sepsis3" in names
        assert "age" in names


class TestHasDerivedSupport:
    """Tests for has_derived_support()."""

    def test_returns_true_for_mimic_iv(self):
        assert has_derived_support("mimic-iv") is True

    def test_returns_false_for_unsupported_dataset(self):
        assert has_derived_support("eicu") is False

    def test_returns_false_for_unknown_dataset(self):
        assert has_derived_support("nonexistent") is False

    def test_returns_false_for_demo(self):
        assert has_derived_support("mimic-iv-demo") is False


class TestGetTablesByCategory:
    """Tests for get_tables_by_category()."""

    def test_returns_dict_of_string_to_list(self):
        result = get_tables_by_category("mimic-iv")
        assert isinstance(result, dict)
        for key, value in result.items():
            assert isinstance(key, str)
            assert isinstance(value, list)
            assert all(isinstance(name, str) for name in value)

    def test_contains_expected_categories(self):
        result = get_tables_by_category("mimic-iv")
        expected = {
            "demographics",
            "score",
            "sepsis",
            "measurement",
            "medication",
            "treatment",
            "organfailure",
            "comorbidity",
            "firstday",
        }
        assert expected.issubset(result.keys())

    def test_total_matches_list_builtins(self):
        categories = get_tables_by_category("mimic-iv")
        total = sum(len(tables) for tables in categories.values())
        assert total == len(list_builtins("mimic-iv"))

    def test_preserves_execution_order_within_categories(self):
        """Tables within each category should appear in execution order."""
        categories = get_tables_by_category("mimic-iv")
        builtins = list_builtins("mimic-iv")
        for tables in categories.values():
            indices = [builtins.index(t) for t in tables]
            assert indices == sorted(indices), (
                f"Tables not in execution order: {tables}"
            )

    def test_unsupported_dataset_raises_value_error(self):
        with pytest.raises(ValueError, match="No built-in derived tables"):
            get_tables_by_category("eicu")

    def test_sofa_in_score_category(self):
        result = get_tables_by_category("mimic-iv")
        assert "sofa" in result.get("score", [])

    def test_sepsis3_in_sepsis_category(self):
        result = get_tables_by_category("mimic-iv")
        assert "sepsis3" in result.get("sepsis", [])


class TestSqlFileIntegrity:
    """Verify vendored SQL files have expected structure."""

    def test_all_sql_files_contain_create_table(self):
        """Each SQL file should contain a CREATE TABLE statement."""
        for path in get_execution_order("mimic-iv"):
            content = path.read_text()
            assert "CREATE TABLE" in content.upper(), (
                f"{path.name} does not contain CREATE TABLE"
            )

    def test_all_sql_files_target_mimiciv_derived_schema(self):
        """Each SQL file should create a table in mimiciv_derived schema."""
        for path in get_execution_order("mimic-iv"):
            content = path.read_text()
            assert "mimiciv_derived" in content, (
                f"{path.name} does not reference mimiciv_derived schema"
            )

    def test_sql_files_contain_drop_table(self):
        """Each SQL file should start with DROP TABLE IF EXISTS for idempotency."""
        for path in get_execution_order("mimic-iv"):
            content = path.read_text()
            assert "DROP TABLE IF EXISTS" in content.upper(), (
                f"{path.name} does not contain DROP TABLE IF EXISTS"
            )

    def test_orchestrator_file_exists(self):
        orchestrator = _BUILTINS_DIR / "mimic_iv" / "duckdb.sql"
        assert orchestrator.exists()

    def test_subdirectory_structure(self):
        """Verify expected subdirectories exist."""
        base = _BUILTINS_DIR / "mimic_iv"
        expected_dirs = [
            "demographics",
            "measurement",
            "comorbidity",
            "medication",
            "treatment",
            "firstday",
            "organfailure",
            "score",
            "sepsis",
        ]
        for d in expected_dirs:
            assert (base / d).is_dir(), f"Expected directory not found: {d}"
