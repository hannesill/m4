"""Tests for cohort builder query_builder module.

Tests cover:
- Empty criteria (no WHERE clause)
- Each criterion in isolation
- Combined criteria
- Validation errors (age boundaries, invalid gender, ICD injection)
- All valid SQL passes is_safe_query()
"""

import pytest

from m4.apps.cohort_builder.query_builder import (
    MAX_AGE,
    MIN_AGE,
    QueryCohortInput,
    build_cohort_count_sql,
    build_cohort_demographics_sql,
    build_gender_distribution_sql,
)
from m4.core.validation import is_safe_query


class TestEmptyCriteria:
    """Test queries with no filtering criteria."""

    def test_count_sql_no_where_clause(self):
        """Empty criteria should produce SQL without WHERE clause."""
        criteria = QueryCohortInput()
        sql = build_cohort_count_sql(criteria)

        assert "WHERE" not in sql
        assert "mimiciv_hosp.patients" in sql
        assert "mimiciv_hosp.admissions" in sql
        assert "patient_count" in sql
        assert "admission_count" in sql

    def test_demographics_sql_no_where_clause(self):
        """Empty criteria should produce demographics SQL without WHERE clause."""
        criteria = QueryCohortInput()
        sql = build_cohort_demographics_sql(criteria)

        assert "WHERE" not in sql
        assert "age_bucket" in sql

    def test_gender_sql_no_where_clause(self):
        """Empty criteria should produce gender SQL without WHERE clause."""
        criteria = QueryCohortInput()
        sql = build_gender_distribution_sql(criteria)

        assert "WHERE" not in sql
        assert "p.gender" in sql

    def test_empty_criteria_passes_validation(self):
        """Empty criteria SQL should pass safety validation."""
        criteria = QueryCohortInput()

        for builder in [
            build_cohort_count_sql,
            build_cohort_demographics_sql,
            build_gender_distribution_sql,
        ]:
            sql = builder(criteria)
            safe, msg = is_safe_query(sql)
            assert safe, f"SQL failed validation: {msg}"


class TestAgeCriteria:
    """Test age filtering criteria."""

    def test_age_min_only(self):
        """age_min should add >= condition."""
        criteria = QueryCohortInput(age_min=18)
        sql = build_cohort_count_sql(criteria)

        assert "WHERE" in sql
        assert "p.anchor_age >= 18" in sql

    def test_age_max_only(self):
        """age_max should add <= condition."""
        criteria = QueryCohortInput(age_max=65)
        sql = build_cohort_count_sql(criteria)

        assert "WHERE" in sql
        assert "p.anchor_age <= 65" in sql

    def test_age_range(self):
        """Both age_min and age_max should create range."""
        criteria = QueryCohortInput(age_min=18, age_max=65)
        sql = build_cohort_count_sql(criteria)

        assert "p.anchor_age >= 18" in sql
        assert "p.anchor_age <= 65" in sql
        assert " AND " in sql

    def test_age_at_boundary_min(self):
        """Age at MIN_AGE boundary should be valid."""
        criteria = QueryCohortInput(age_min=MIN_AGE)
        sql = build_cohort_count_sql(criteria)

        assert f"p.anchor_age >= {MIN_AGE}" in sql

    def test_age_at_boundary_max(self):
        """Age at MAX_AGE boundary should be valid."""
        criteria = QueryCohortInput(age_max=MAX_AGE)
        sql = build_cohort_count_sql(criteria)

        assert f"p.anchor_age <= {MAX_AGE}" in sql


class TestAgeValidation:
    """Test age validation errors."""

    def test_age_min_negative(self):
        """Negative age_min should raise ValueError."""
        criteria = QueryCohortInput(age_min=-1)

        with pytest.raises(ValueError, match="age_min must be between"):
            build_cohort_count_sql(criteria)

    def test_age_max_negative(self):
        """Negative age_max should raise ValueError."""
        criteria = QueryCohortInput(age_max=-1)

        with pytest.raises(ValueError, match="age_max must be between"):
            build_cohort_count_sql(criteria)

    def test_age_min_too_high(self):
        """age_min above MAX_AGE should raise ValueError."""
        criteria = QueryCohortInput(age_min=MAX_AGE + 1)

        with pytest.raises(ValueError, match="age_min must be between"):
            build_cohort_count_sql(criteria)

    def test_age_max_too_high(self):
        """age_max above MAX_AGE should raise ValueError."""
        criteria = QueryCohortInput(age_max=MAX_AGE + 1)

        with pytest.raises(ValueError, match="age_max must be between"):
            build_cohort_count_sql(criteria)

    def test_age_min_greater_than_max(self):
        """age_min > age_max should raise ValueError."""
        criteria = QueryCohortInput(age_min=65, age_max=18)

        with pytest.raises(ValueError, match="cannot be greater than"):
            build_cohort_count_sql(criteria)


class TestGenderCriteria:
    """Test gender filtering criteria."""

    def test_gender_male(self):
        """Gender 'M' should add proper condition."""
        criteria = QueryCohortInput(gender="M")
        sql = build_cohort_count_sql(criteria)

        assert "p.gender = 'M'" in sql

    def test_gender_female(self):
        """Gender 'F' should add proper condition."""
        criteria = QueryCohortInput(gender="F")
        sql = build_cohort_count_sql(criteria)

        assert "p.gender = 'F'" in sql


class TestGenderValidation:
    """Test gender validation errors."""

    def test_invalid_gender_x(self):
        """Invalid gender 'X' should raise ValueError."""
        criteria = QueryCohortInput(gender="X")

        with pytest.raises(ValueError, match="gender must be one of"):
            build_cohort_count_sql(criteria)

    def test_invalid_gender_lowercase(self):
        """Lowercase gender 'm' should raise ValueError."""
        criteria = QueryCohortInput(gender="m")

        with pytest.raises(ValueError, match="gender must be one of"):
            build_cohort_count_sql(criteria)

    def test_invalid_gender_empty(self):
        """Empty gender string should raise ValueError."""
        criteria = QueryCohortInput(gender="")

        with pytest.raises(ValueError, match="gender must be one of"):
            build_cohort_count_sql(criteria)


class TestIcdCodesCriteria:
    """Test ICD codes filtering criteria."""

    def test_single_icd_code(self):
        """Single ICD code should create EXISTS subquery."""
        criteria = QueryCohortInput(icd_codes=["I10"])
        sql = build_cohort_count_sql(criteria)

        assert "EXISTS" in sql
        assert "mimiciv_hosp.diagnoses_icd" in sql
        assert "icd_code LIKE 'I10%'" in sql

    def test_multiple_icd_codes(self):
        """Multiple ICD codes should create OR conditions."""
        criteria = QueryCohortInput(icd_codes=["I10", "E11"])
        sql = build_cohort_count_sql(criteria)

        assert "icd_code LIKE 'I10%'" in sql
        assert "icd_code LIKE 'E11%'" in sql
        assert " OR " in sql

    def test_icd_code_with_dot(self):
        """ICD code with dot should be valid."""
        criteria = QueryCohortInput(icd_codes=["E11.9"])
        sql = build_cohort_count_sql(criteria)

        assert "icd_code LIKE 'E11.9%'" in sql

    def test_icd_match_all_single_code(self):
        """Single ICD code with match_all should create single EXISTS."""
        criteria = QueryCohortInput(icd_codes=["I10"], icd_match_all=True)
        sql = build_cohort_count_sql(criteria)

        assert "EXISTS" in sql
        assert "icd_code LIKE 'I10%'" in sql
        assert " OR " not in sql

    def test_icd_match_all_multiple_codes(self):
        """Multiple ICD codes with match_all should create separate EXISTS for each."""
        criteria = QueryCohortInput(icd_codes=["I10", "E11"], icd_match_all=True)
        sql = build_cohort_count_sql(criteria)

        # Each code should have its own EXISTS clause
        assert sql.count("EXISTS") == 2
        assert "icd_code LIKE 'I10%'" in sql
        assert "icd_code LIKE 'E11%'" in sql
        # Should not use OR to combine them
        assert " OR " not in sql or "OR" not in sql.split("diagnoses_icd")[1]

    def test_icd_match_any_is_default(self):
        """Without icd_match_all, should use OR (default behavior)."""
        criteria = QueryCohortInput(icd_codes=["I10", "E11"])
        sql = build_cohort_count_sql(criteria)

        # Should have single EXISTS with OR
        assert sql.count("EXISTS") == 1
        assert " OR " in sql


class TestIcdCodesValidation:
    """Test ICD codes validation errors."""

    def test_icd_injection_semicolon(self):
        """ICD code with semicolon should raise ValueError."""
        criteria = QueryCohortInput(icd_codes=["I10; DROP TABLE"])

        with pytest.raises(ValueError, match="Invalid ICD code format"):
            build_cohort_count_sql(criteria)

    def test_icd_injection_quote(self):
        """ICD code with quote should raise ValueError."""
        criteria = QueryCohortInput(icd_codes=["I10'"])

        with pytest.raises(ValueError, match="Invalid ICD code format"):
            build_cohort_count_sql(criteria)

    def test_icd_injection_dash(self):
        """ICD code with SQL comment should raise ValueError."""
        criteria = QueryCohortInput(icd_codes=["I10--"])

        with pytest.raises(ValueError, match="Invalid ICD code format"):
            build_cohort_count_sql(criteria)

    def test_icd_empty_string(self):
        """Empty ICD code string should raise ValueError."""
        criteria = QueryCohortInput(icd_codes=[""])

        with pytest.raises(ValueError, match="cannot be empty"):
            build_cohort_count_sql(criteria)

    def test_icd_empty_list_is_valid(self):
        """Empty ICD codes list should not add condition."""
        criteria = QueryCohortInput(icd_codes=[])
        sql = build_cohort_count_sql(criteria)

        assert "diagnoses_icd" not in sql


class TestIcuStayCriteria:
    """Test ICU stay filtering criteria."""

    def test_has_icu_stay_true(self):
        """has_icu_stay=True should add EXISTS subquery."""
        criteria = QueryCohortInput(has_icu_stay=True)
        sql = build_cohort_count_sql(criteria)

        assert "EXISTS" in sql
        assert "mimiciv_icu.icustays" in sql
        assert "NOT EXISTS" not in sql

    def test_has_icu_stay_false(self):
        """has_icu_stay=False should add NOT EXISTS subquery."""
        criteria = QueryCohortInput(has_icu_stay=False)
        sql = build_cohort_count_sql(criteria)

        assert "NOT EXISTS" in sql
        assert "mimiciv_icu.icustays" in sql


class TestMortalityCriteria:
    """Test in-hospital mortality filtering criteria."""

    def test_mortality_true(self):
        """in_hospital_mortality=True should filter for deaths."""
        criteria = QueryCohortInput(in_hospital_mortality=True)
        sql = build_cohort_count_sql(criteria)

        assert "hospital_expire_flag = 1" in sql

    def test_mortality_false(self):
        """in_hospital_mortality=False should filter for survivors."""
        criteria = QueryCohortInput(in_hospital_mortality=False)
        sql = build_cohort_count_sql(criteria)

        assert "hospital_expire_flag = 0" in sql


class TestCombinedCriteria:
    """Test multiple criteria combined."""

    def test_age_and_gender(self):
        """Age and gender criteria combined."""
        criteria = QueryCohortInput(age_min=18, age_max=65, gender="M")
        sql = build_cohort_count_sql(criteria)

        assert "p.anchor_age >= 18" in sql
        assert "p.anchor_age <= 65" in sql
        assert "p.gender = 'M'" in sql

    def test_all_criteria(self):
        """All criteria combined."""
        criteria = QueryCohortInput(
            age_min=18,
            age_max=80,
            gender="F",
            icd_codes=["I10", "E11"],
            has_icu_stay=True,
            in_hospital_mortality=False,
        )
        sql = build_cohort_count_sql(criteria)

        assert "p.anchor_age >= 18" in sql
        assert "p.anchor_age <= 80" in sql
        assert "p.gender = 'F'" in sql
        assert "diagnoses_icd" in sql
        assert "icd_code LIKE 'I10%'" in sql
        assert "mimiciv_icu.icustays" in sql
        assert "EXISTS" in sql
        assert "hospital_expire_flag = 0" in sql

    def test_combined_criteria_pass_validation(self):
        """Combined criteria SQL should pass safety validation."""
        criteria = QueryCohortInput(
            age_min=18,
            age_max=80,
            gender="F",
            icd_codes=["I10", "E11.9", "J18"],
            has_icu_stay=True,
            in_hospital_mortality=False,
        )

        for builder in [
            build_cohort_count_sql,
            build_cohort_demographics_sql,
            build_gender_distribution_sql,
        ]:
            sql = builder(criteria)
            safe, msg = is_safe_query(sql)
            assert safe, f"SQL failed validation: {msg}"


class TestSqlSafety:
    """Test that all generated SQL passes is_safe_query()."""

    @pytest.mark.parametrize(
        "criteria",
        [
            QueryCohortInput(),
            QueryCohortInput(age_min=0),
            QueryCohortInput(age_max=130),
            QueryCohortInput(gender="M"),
            QueryCohortInput(icd_codes=["A00"]),
            QueryCohortInput(icd_codes=["A00.1", "B99.9", "Z87"]),
            QueryCohortInput(icd_codes=["I10", "E11"], icd_match_all=True),
            QueryCohortInput(icd_codes=["I10", "E11"], icd_match_all=False),
            QueryCohortInput(has_icu_stay=True),
            QueryCohortInput(has_icu_stay=False),
            QueryCohortInput(in_hospital_mortality=True),
            QueryCohortInput(in_hospital_mortality=False),
            QueryCohortInput(
                age_min=18,
                age_max=65,
                gender="F",
                icd_codes=["I10"],
                has_icu_stay=True,
                in_hospital_mortality=True,
            ),
            QueryCohortInput(
                age_min=18,
                age_max=65,
                gender="F",
                icd_codes=["I10", "E11"],
                icd_match_all=True,
                has_icu_stay=True,
                in_hospital_mortality=True,
            ),
        ],
    )
    def test_sql_passes_safety_check(self, criteria):
        """All valid criteria should produce safe SQL."""
        for builder in [
            build_cohort_count_sql,
            build_cohort_demographics_sql,
            build_gender_distribution_sql,
        ]:
            sql = builder(criteria)
            safe, msg = is_safe_query(sql)
            assert safe, f"SQL failed validation for {criteria}: {msg}\nSQL: {sql}"
