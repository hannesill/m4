# Task: Calculate Minimum GCS (eICU)

Calculate the minimum Glasgow Coma Scale (GCS) score for each ICU stay
using data from the first 24 hours (from 6 hours before ICU admission
to 24 hours after admission) (Teasdale & Jennett, Lancet, 1974).

When a component is missing at a given timepoint, assume normal for
that component. If no GCS data exists at all for a stay, default to
normal (gcs_min=15, eyes=4, verbal=5, motor=6).

When a charted total GCS value is available and within the valid range
(3-15), use it as the total; otherwise compute total from
motor + verbal + eyes. If multiple timepoints share the same minimum
total GCS, use the row with the earliest chart offset.

Report the minimum total GCS and the component values at the time of
the minimum total score.

Output a CSV file to `{output_path}` with these exact columns:
patientunitstayid, uniquepid, patienthealthsystemstayid, gcs_min, gcs_motor, gcs_verbal, gcs_eyes

One row per ICU stay.
