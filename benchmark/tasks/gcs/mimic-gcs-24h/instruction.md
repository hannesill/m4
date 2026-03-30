# Task: Calculate Minimum GCS

You have access to a MIMIC-IV clinical database (DuckDB) at `{db_path}`.
It contains ICU patient data with schemas `mimiciv_hosp`, `mimiciv_icu`,
and pre-computed intermediate tables in `mimiciv_derived`.

Calculate the minimum Glasgow Coma Scale (GCS) score for each ICU stay
using data from the first 24 hours (from 6 hours before ICU admission
to 24 hours after admission) (Teasdale & Jennett, Lancet, 1974).

GCS has 3 components:
- **Eye opening** (1-4): None=1, To pain=2, To voice=3, Spontaneous=4
- **Verbal response** (1-5): None=1, Incomprehensible=2, Inappropriate=3, Confused=4, Oriented=5
- **Motor response** (1-6): None=1, Extension=2, Flexion=3, Withdrawal=4, Localizing=5, Obeys=6

Total GCS = Eye + Verbal + Motor (range 3-15).

For intubated patients unable to give a verbal response, assume
unimpaired consciousness (GCS = 15). When a component is missing, use
the most recent value within 6 hours. If no value exists, default to
normal (eyes=4, verbal=5, motor=6).

Report the minimum total GCS and the component values at the time of
the minimum total score.

Output a CSV file to `{output_path}` with these exact columns:
subject_id, hadm_id, stay_id, gcs_min, gcs_motor, gcs_verbal, gcs_eyes

One row per ICU stay.
