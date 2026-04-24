# Task: Calculate Minimum GCS (Raw Tables)

The target table and task-relevant upstream derived tables have been removed.
Other non-target derived tables may still be present; do not use them as a
shortcut for the requested GCS calculation.

Calculate the minimum Glasgow Coma Scale (GCS) score for each ICU stay
using data from the first 24 hours (from 6 hours before ICU admission
to 24 hours after admission) (Teasdale & Jennett, Lancet, 1974).

For intubated patients who cannot give a verbal response, the verbal
component is untestable and the total GCS is assumed to be 15
(unimpaired consciousness).

When a component is missing at a given time, use the most recent value
within 6 hours. If no GCS data exists at all for a stay, default to
normal (gcs_min=15, eyes=4, verbal=5, motor=6).

Report the minimum total GCS and the component values at the time of
the minimum total score.

Output a CSV file to `{output_path}` with these exact columns:
subject_id, hadm_id, stay_id, gcs_min, gcs_motor, gcs_verbal, gcs_eyes

One row per ICU stay.
