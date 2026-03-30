# Task: Calculate SAPS-II Score (Raw Tables)

You have access to a MIMIC-IV clinical database (DuckDB) at `{db_path}`.
It contains ICU patient data with schemas `mimiciv_hosp` and `mimiciv_icu`.
There are no pre-computed intermediate or derived tables.

Calculate the Simplified Acute Physiology Score II (SAPS-II) for each
ICU stay using the worst values from the first 24 hours of ICU admission.
Compute directly from base tables such as `chartevents`, `labevents`,
`outputevents`, and hospital tables (Le Gall et al., JAMA, 1993).

SAPS-II uses 15 weighted components:

| Variable | Points | Scoring Logic |
|----------|--------|---------------|
| Age | 0-18 | 0 (<40), 7 (40-59), 12 (60-69), 15 (70-74), 16 (75-79), 18 (>=80) |
| Heart Rate | 0-11 | 11 (<40 bpm), 2 (40-69), 0 (70-119), 4 (120-159), 7 (>=160) |
| Systolic BP | 0-13 | 13 (<70 mmHg), 5 (70-99), 0 (100-199), 2 (>=200) |
| Temperature | 0-3 | 0 (<39°C), 3 (>=39°C) |
| PaO2/FiO2 (if ventilated or CPAP) | 0-11 | 11 (<100), 9 (100-199), 6 (>=200); 0 if not ventilated |
| Urine Output | 0-11 | 11 (<500 mL/day), 4 (500-999), 0 (>=1000) |
| BUN | 0-10 | 0 (<28 mg/dL), 6 (28-83), 10 (>=84) |
| WBC | 0-12 | 12 (<1 x10^9/L), 0 (1-19), 3 (>=20) |
| Potassium | 0-3 | 3 (<3 or >=5 mEq/L), 0 (3-4.9) |
| Sodium | 0-5 | 5 (<125 mEq/L), 0 (125-144), 1 (>=145) |
| Bicarbonate | 0-6 | 6 (<15 mEq/L), 3 (15-19), 0 (>=20) |
| Bilirubin | 0-9 | 0 (<4 mg/dL), 4 (4-5.9), 9 (>=6) |
| GCS | 0-26 | 0 (14-15), 5 (11-13), 7 (9-10), 13 (6-8), 26 (<6) |
| Chronic Disease | 0-17 | 17 (AIDS), 10 (Hematologic malignancy), 9 (Metastatic cancer), 0 (none) |
| Admission Type | 0-8 | 0 (Scheduled surgical), 6 (Medical), 8 (Unscheduled surgical) |

The total SAPS-II score ranges from 0 to 163. Treat missing data as
normal (score 0).

Output a CSV file to `{output_path}` with these exact columns:
subject_id, hadm_id, stay_id, sapsii, age_score, hr_score, sysbp_score,
temp_score, pao2fio2_score, uo_score, bun_score, wbc_score, potassium_score,
sodium_score, bicarbonate_score, bilirubin_score, gcs_score, comorbidity_score,
admissiontype_score

One row per ICU stay. The `sapsii` column is the sum of the 15 component scores.
