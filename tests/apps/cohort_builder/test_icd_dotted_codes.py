"""Dotted ICD codes against diagnoses_icd as MIMIC-IV stores it (no dots)."""

import duckdb
import pytest

from m4.apps.cohort_builder.query_builder import (
    QueryCohortInput,
    build_cohort_count_sql,
)


@pytest.fixture
def con():
    con = duckdb.connect()
    con.execute("CREATE SCHEMA mimiciv_hosp")
    con.execute(
        "CREATE TABLE mimiciv_hosp.patients AS "
        "SELECT * FROM (VALUES (1, 'F', 60), (2, 'M', 70), (3, 'F', 80)) "
        "t(subject_id, gender, anchor_age)"
    )
    con.execute(
        "CREATE TABLE mimiciv_hosp.admissions AS "
        "SELECT * FROM (VALUES (101, 1, 0), (102, 2, 0), (103, 3, 1)) "
        "t(hadm_id, subject_id, hospital_expire_flag)"
    )
    con.execute(
        "CREATE TABLE mimiciv_hosp.diagnoses_icd AS "
        "SELECT * FROM (VALUES (101, 'E119', 10), (101, 'I10', 10), "
        "(102, '4019', 9), (103, 'E1165', 10)) t(hadm_id, icd_code, icd_version)"
    )
    yield con
    con.close()


def _patient_count(con, **criteria) -> int:
    sql = build_cohort_count_sql(QueryCohortInput(**criteria))
    return con.execute(sql).fetchone()[0]


@pytest.mark.parametrize(
    ("dotted", "plain", "expected"),
    [("E11.9", "E119", 1), ("401.9", "4019", 1), ("E11.", "E11", 2)],
)
def test_dotted_code_matches_like_undotted(con, dotted, plain, expected):
    assert _patient_count(con, icd_codes=[plain]) == expected
    assert _patient_count(con, icd_codes=[dotted]) == expected


def test_dotted_codes_with_match_all(con):
    assert _patient_count(con, icd_codes=["E11.9", "I10"], icd_match_all=True) == 1


def test_code_of_only_dots_rejected():
    with pytest.raises(ValueError, match="Invalid ICD code format"):
        build_cohort_count_sql(QueryCohortInput(icd_codes=["."]))
