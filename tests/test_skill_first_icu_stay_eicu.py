"""The eICU script of the first-icu-stay skill, run on a hand-built patient table."""

from pathlib import Path

import duckdb
import pytest

import m4.skills

SCRIPT = (
    Path(m4.skills.__file__).parent
    / "clinical"
    / "first-icu-stay"
    / "scripts"
    / "eicu"
    / "icustay_detail.sql"
)

# (patientunitstayid, patienthealthsystemstayid, uniquepid, hospitaldischargeyear,
#  hospitaladmitoffset, unitvisitnumber, unitdischargeoffset, age)
PATIENT_ROWS = [
    # A: one hospital stay, two unit stays. The later stay has the smaller
    # unit stay id and the more negative offset.
    (11, 100, "A", 2014, -5000, 2, 1440, "70"),
    (12, 100, "A", 2014, -60, 1, 2880, "70"),
    # B: hospital stays in different years, so their order is known.
    (21, 200, "B", 2014, -10, 1, 1440, "> 89"),
    (22, 201, "B", 2015, -10, 1, 1440, "> 89"),
    # C: two hospital stays in the same year, so their order is unknown.
    (31, 300, "C", 2015, -10, 1, 1440, "55"),
    (32, 301, "C", 2015, -10, 1, 1440, "55"),
    # D: no unit stay with unitvisitnumber = 1 in the data.
    (41, 400, "D", 2014, -300, 2, 1440, None),
    # E: a zero-length unit stay shares its offset with the stay after it.
    (51, 500, "E", 2014, -90, 1, 0, "40"),
    (52, 500, "E", 2014, -90, 2, 720, "40"),
]


@pytest.fixture
def detail():
    con = duckdb.connect()
    con.execute("CREATE SCHEMA eicu_crd")
    con.execute(
        """
        CREATE TABLE eicu_crd.patient (
            patientunitstayid BIGINT, patienthealthsystemstayid BIGINT,
            uniquepid VARCHAR, hospitaldischargeyear BIGINT,
            hospitaladmitoffset BIGINT, unitvisitnumber BIGINT,
            unitdischargeoffset BIGINT, age VARCHAR,
            gender VARCHAR, ethnicity VARCHAR, hospitalid BIGINT,
            hospitaldischargeoffset BIGINT, hospitaldischargestatus VARCHAR,
            unittype VARCHAR, unitstaytype VARCHAR, unitdischargestatus VARCHAR
        )
        """
    )
    con.executemany(
        """
        INSERT INTO eicu_crd.patient VALUES
        (?, ?, ?, ?, ?, ?, ?, ?, 'Female', 'Caucasian', 1, 10000, 'Alive',
         'MICU', 'admit', 'Alive')
        """,
        PATIENT_ROWS,
    )
    rows = con.execute(SCRIPT.read_text()).df()
    con.close()
    return rows.set_index("patientunitstayid")


def test_one_row_per_unit_stay(detail):
    assert sorted(detail.index) == sorted(row[0] for row in PATIENT_ROWS)


def test_unit_stays_are_ordered_by_offset_not_by_id(detail):
    assert detail.loc[12, "icustay_seq"] == 1
    assert detail.loc[12, "first_icu_stay"]
    assert detail.loc[11, "icustay_seq"] == 2
    assert not detail.loc[11, "first_icu_stay"]


def test_hospital_stays_in_different_years_are_ordered(detail):
    assert detail.loc[21, "first_hosp_stay"] == True  # noqa: E712
    assert detail.loc[22, "first_hosp_stay"] == False  # noqa: E712
    assert detail.loc[22, "hospstay_seq"] == 2


def test_hospital_stays_in_the_same_year_have_no_first(detail):
    assert detail.loc[[31, 32], "first_hosp_stay"].isna().all()
    assert (detail.loc[[31, 32], "hospstays_in_year"] == 2).all()
    # Each is still the first ICU stay of its own hospital stay.
    assert detail.loc[[31, 32], "first_icu_stay"].all()


def test_hospital_stay_without_visit_one_keeps_a_first_icu_stay(detail):
    assert detail.loc[41, "unitvisitnumber"] == 2
    assert detail.loc[41, "first_icu_stay"]


def test_equal_offsets_fall_back_to_visit_number(detail):
    assert detail.loc[51, "icustay_seq"] == 1
    assert detail.loc[52, "icustay_seq"] == 2


def test_every_hospital_stay_has_exactly_one_first_icu_stay(detail):
    firsts = detail.groupby("patienthealthsystemstayid")["first_icu_stay"].sum()
    assert (firsts == 1).all()


def test_age_text_becomes_a_number(detail):
    assert detail.loc[12, "admission_age"] == 70
    assert detail.loc[21, "admission_age"] == 90
    assert detail["admission_age"].isna()[41]
