"""SQL query builder for cohort criteria.

This module generates validated SQL queries for cohort filtering based on
user-provided criteria. All generated SQL is validated against injection
attacks before execution.

Phase 1 supports: age_min, age_max, gender
Phase 2 will add: icd_codes, has_icu_stay, in_hospital_mortality
"""

from dataclasses import dataclass

from m4.core.tools.base import ToolInput

# Valid gender values
VALID_GENDERS = frozenset({"M", "F"})

# Age validation bounds
MIN_AGE = 0
MAX_AGE = 130


@dataclass
class QueryCohortInput(ToolInput):
    """Input parameters for cohort queries.

    All fields are optional - an empty query returns total counts.

    Attributes:
        age_min: Minimum patient age (inclusive), 0-130
        age_max: Maximum patient age (inclusive), 0-130
        gender: Patient gender ('M' or 'F')
    """

    age_min: int | None = None
    age_max: int | None = None
    gender: str | None = None


def _validate_criteria(criteria: QueryCohortInput) -> None:
    """Validate criteria values before SQL generation.

    Args:
        criteria: The cohort criteria to validate

    Raises:
        ValueError: If any criteria value is invalid
    """
    if criteria.age_min is not None:
        if not isinstance(criteria.age_min, int):
            raise ValueError(
                f"age_min must be an integer, got {type(criteria.age_min)}"
            )
        if criteria.age_min < MIN_AGE or criteria.age_min > MAX_AGE:
            raise ValueError(f"age_min must be between {MIN_AGE} and {MAX_AGE}")

    if criteria.age_max is not None:
        if not isinstance(criteria.age_max, int):
            raise ValueError(
                f"age_max must be an integer, got {type(criteria.age_max)}"
            )
        if criteria.age_max < MIN_AGE or criteria.age_max > MAX_AGE:
            raise ValueError(f"age_max must be between {MIN_AGE} and {MAX_AGE}")

    if criteria.age_min is not None and criteria.age_max is not None:
        if criteria.age_min > criteria.age_max:
            raise ValueError(
                f"age_min ({criteria.age_min}) cannot be greater than "
                f"age_max ({criteria.age_max})"
            )

    if criteria.gender is not None:
        if not isinstance(criteria.gender, str):
            raise ValueError(f"gender must be a string, got {type(criteria.gender)}")
        if criteria.gender not in VALID_GENDERS:
            raise ValueError(
                f"gender must be one of {sorted(VALID_GENDERS)}, got '{criteria.gender}'"
            )


def build_cohort_count_sql(criteria: QueryCohortInput) -> str:
    """Build SQL query for cohort patient and admission counts.

    Args:
        criteria: Cohort filtering criteria

    Returns:
        SQL query string that returns patient_count and admission_count

    Raises:
        ValueError: If criteria validation fails
    """
    _validate_criteria(criteria)

    # Build WHERE clauses
    where_clauses: list[str] = []

    if criteria.age_min is not None:
        where_clauses.append(f"p.anchor_age >= {criteria.age_min}")

    if criteria.age_max is not None:
        where_clauses.append(f"p.anchor_age <= {criteria.age_max}")

    if criteria.gender is not None:
        # Gender is validated against VALID_GENDERS, safe to interpolate
        where_clauses.append(f"p.gender = '{criteria.gender}'")

    # Build the query
    sql = """SELECT
    COUNT(DISTINCT p.subject_id) AS patient_count,
    COUNT(DISTINCT a.hadm_id) AS admission_count
FROM mimiciv_hosp.patients p
JOIN mimiciv_hosp.admissions a ON p.subject_id = a.subject_id"""

    if where_clauses:
        sql += "\nWHERE " + " AND ".join(where_clauses)

    return sql


def build_cohort_demographics_sql(criteria: QueryCohortInput) -> str:
    """Build SQL query for cohort demographic distributions.

    Returns age distribution (10-year buckets) and gender counts.

    Args:
        criteria: Cohort filtering criteria

    Returns:
        SQL query string that returns demographic distributions

    Raises:
        ValueError: If criteria validation fails
    """
    _validate_criteria(criteria)

    # Build WHERE clauses (same as count query)
    where_clauses: list[str] = []

    if criteria.age_min is not None:
        where_clauses.append(f"p.anchor_age >= {criteria.age_min}")

    if criteria.age_max is not None:
        where_clauses.append(f"p.anchor_age <= {criteria.age_max}")

    if criteria.gender is not None:
        where_clauses.append(f"p.gender = '{criteria.gender}'")

    where_clause = ""
    if where_clauses:
        where_clause = "WHERE " + " AND ".join(where_clauses)

    # Age buckets query
    age_sql = f"""SELECT
    CASE
        WHEN p.anchor_age < 20 THEN '0-19'
        WHEN p.anchor_age < 30 THEN '20-29'
        WHEN p.anchor_age < 40 THEN '30-39'
        WHEN p.anchor_age < 50 THEN '40-49'
        WHEN p.anchor_age < 60 THEN '50-59'
        WHEN p.anchor_age < 70 THEN '60-69'
        WHEN p.anchor_age < 80 THEN '70-79'
        WHEN p.anchor_age < 90 THEN '80-89'
        ELSE '90+'
    END AS age_bucket,
    COUNT(DISTINCT p.subject_id) AS patient_count
FROM mimiciv_hosp.patients p
JOIN mimiciv_hosp.admissions a ON p.subject_id = a.subject_id
{where_clause}
GROUP BY age_bucket
ORDER BY age_bucket"""

    return age_sql


def build_gender_distribution_sql(criteria: QueryCohortInput) -> str:
    """Build SQL query for gender distribution.

    Args:
        criteria: Cohort filtering criteria

    Returns:
        SQL query string that returns gender counts

    Raises:
        ValueError: If criteria validation fails
    """
    _validate_criteria(criteria)

    # Build WHERE clauses
    where_clauses: list[str] = []

    if criteria.age_min is not None:
        where_clauses.append(f"p.anchor_age >= {criteria.age_min}")

    if criteria.age_max is not None:
        where_clauses.append(f"p.anchor_age <= {criteria.age_max}")

    if criteria.gender is not None:
        where_clauses.append(f"p.gender = '{criteria.gender}'")

    where_clause = ""
    if where_clauses:
        where_clause = "WHERE " + " AND ".join(where_clauses)

    sql = f"""SELECT
    p.gender,
    COUNT(DISTINCT p.subject_id) AS patient_count
FROM mimiciv_hosp.patients p
JOIN mimiciv_hosp.admissions a ON p.subject_id = a.subject_id
{where_clause}
GROUP BY p.gender
ORDER BY p.gender"""

    return sql
