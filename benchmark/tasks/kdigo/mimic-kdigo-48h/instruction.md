# Task: KDIGO AKI Staging

You have access to a MIMIC-IV clinical database (DuckDB) at `{db_path}`.
It contains ICU patient data with schemas `mimiciv_hosp`, `mimiciv_icu`,
and pre-computed intermediate tables in `mimiciv_derived`.

Determine the maximum KDIGO Acute Kidney Injury (AKI) stage for each ICU
stay within the first 48 hours of admission.

KDIGO stages AKI on a 0-3 scale using three independent criteria:

**Creatinine criteria** (compare to baseline = minimum in prior 7 days):
- Stage 1: >= 1.5x baseline OR >= baseline (48h) + 0.3 mg/dL
- Stage 2: >= 2.0x baseline
- Stage 3: >= 3.0x baseline OR (creatinine >= 4.0 with acute rise)

**Urine output criteria** (weight-normalized, mL/kg/h):
- Stage 1: < 0.5 mL/kg/h for 6-12 hours
- Stage 2: < 0.5 mL/kg/h for >= 12 hours
- Stage 3: < 0.3 mL/kg/h for >= 24 hours OR anuria for >= 12 hours

**CRRT**: Any continuous renal replacement therapy = Stage 3

The final AKI stage is the maximum across all three criteria.
Treat missing data as no AKI (stage 0).

Output a CSV file to `{output_path}` with these exact columns:
subject_id, hadm_id, stay_id, aki_stage, aki_stage_creat, aki_stage_uo, aki_stage_crrt

One row per ICU stay. Each stage column ranges from 0 to 3.
