# Task: Calculate Minimum GCS (eICU)

You have access to an eICU Collaborative Research Database (DuckDB) at `{db_path}`.
It contains ICU patient data from 208 US hospitals in the `main` schema.
There are no pre-computed derived tables — you must work from raw tables.

Key tables: `patient` (demographics + ICU stay info), `nursecharting`
(bedside observations), `apacheapsvar` (APACHE physiology variables).

**Important eICU conventions:**
- The primary ICU stay identifier is `patientunitstayid`
- Time is in **offset minutes** from ICU admission (not timestamps).
  `nursingchartoffset = 0` means ICU admission time.
- Patient identifiers: `uniquepid` (patient), `patienthealthsystemstayid`
  (hospital stay), `patientunitstayid` (ICU stay)

Calculate the minimum Glasgow Coma Scale (GCS) score for each ICU stay
using data from the first 24 hours (from 6 hours before ICU admission
to 24 hours after admission) (Teasdale & Jennett, Lancet, 1974).

GCS has 3 components:
- **Eye opening** (1-4): None=1, To pain=2, To voice=3, Spontaneous=4
- **Verbal response** (1-5): None=1, Incomprehensible=2, Inappropriate=3, Confused=4, Oriented=5
- **Motor response** (1-6): None=1, Extension=2, Flexion=3, Withdrawal=4, Localizing=5, Obeys=6

Total GCS = Eye + Verbal + Motor (range 3-15).

When a component is missing at a given timepoint, assume normal for
that component. If no GCS data exists at all for a stay, default to
normal (gcs_min=15, eyes=4, verbal=5, motor=6).

Report the minimum total GCS and the component values at the time of
the minimum total score.

Output a CSV file to `{output_path}` with these exact columns:
patientunitstayid, uniquepid, patienthealthsystemstayid, gcs_min, gcs_motor, gcs_verbal, gcs_eyes

One row per ICU stay.
