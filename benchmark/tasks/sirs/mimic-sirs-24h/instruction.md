# Task: Calculate SIRS Criteria

You have access to a MIMIC-IV clinical database (DuckDB) at `{db_path}`.
It contains ICU patient data with schemas `mimiciv_hosp`, `mimiciv_icu`,
and pre-computed intermediate tables in `mimiciv_derived`.

Calculate the Systemic Inflammatory Response Syndrome (SIRS) criteria
for each ICU stay using data from the first 24 hours (from 6 hours
before ICU admission to 24 hours after admission).

SIRS scores the body's inflammatory response on 4 binary criteria:

| Criterion | Abnormal Threshold |
|-----------|-------------------|
| Temperature | < 36°C OR > 38°C |
| Heart Rate | > 90 bpm |
| Respiratory | RR > 20/min OR PaCO2 < 32 mmHg |
| WBC | < 4 OR > 12 ×10⁹/L OR > 10% bands |

Each criterion met scores 1 point. The total SIRS score ranges from 0 to 4.
Treat missing data as normal (score 0).

Output a CSV file to `{output_path}` with these exact columns:
subject_id, hadm_id, stay_id, sirs, temp_score, heart_rate_score, resp_score, wbc_score

One row per ICU stay. The `sirs` column is the sum of the four component scores.
