# Task: KDIGO AKI Staging (Raw Tables)

The target table and task-relevant upstream derived tables have been removed.
Other non-target derived tables may still be present; do not use them as a
shortcut for the requested KDIGO staging calculation.

Determine the maximum KDIGO Acute Kidney Injury (AKI) stage for each
ICU stay within the first 48 hours of admission
(KDIGO Clinical Practice Guideline, Kidney International Supplements, 2012).

The final AKI stage is the maximum across creatinine criteria, urine
output criteria, and CRRT. Treat missing data as no AKI (stage 0).

Output a CSV file to `{output_path}` with these exact columns:
subject_id, hadm_id, stay_id, aki_stage, aki_stage_creat, aki_stage_uo, aki_stage_crrt

One row per ICU stay. Each stage column ranges from 0 to 3.
