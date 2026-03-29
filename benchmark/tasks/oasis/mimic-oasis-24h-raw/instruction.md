# Task: Calculate OASIS Score (Raw Tables)

You have access to a MIMIC-IV clinical database (DuckDB) at `{db_path}`.
It contains ICU patient data with schemas `mimiciv_hosp` and `mimiciv_icu`.

Calculate the Oxford Acute Severity of Illness Score (OASIS) for each
ICU stay using data from the first 24 hours of ICU admission. Compute
directly from the raw `chartevents` and `outputevents` tables.

OASIS uses 10 components (no laboratory values required):

| Variable | Points | Scoring Logic |
|----------|--------|---------------|
| Pre-ICU LOS (minutes from hospital admit to ICU) | 0-5 | 5 (<10.2), 3 (10.2-296), 0 (297-1439), 2 (1440-18707), 1 (>=18708) |
| Age | 0-9 | 0 (<24), 3 (24-53), 6 (54-77), 9 (78-89), 7 (>=90) |
| GCS | 0-10 | 10 (<=7), 4 (8-13), 3 (14), 0 (15) |
| Heart Rate | 0-6 | 6 (>125 bpm), 4 (<33), 3 (107-125), 1 (89-106), 0 (33-88) |
| Mean BP | 0-4 | 4 (<20.65 mmHg), 3 (<51 or >143.44), 2 (51-61.33), 0 (61.33-143.44) |
| Respiratory Rate | 0-10 | 10 (<6), 9 (>44), 6 (>30), 1 (>22 or <13), 0 (13-22) |
| Temperature | 0-6 | 6 (>39.88°C), 4 (33.22-35.93), 3 (<33.22), 2 (35.93-36.39 or 36.89-39.88), 0 (36.39-36.89) |
| Urine Output (mL/day) | 0-10 | 10 (<671), 8 (>6897), 5 (671-1427), 1 (1427-2544), 0 (2544-6897) |
| Mechanical Ventilation | 0-9 | 9 (ventilated), 0 (not ventilated) |
| Elective Surgery | 0-6 | 0 (elective surgical admission), 6 (all others) |

Mechanical ventilation means invasive ventilation during the first 24 hours.
Elective surgery requires both elective admission type AND a surgical service.
Treat missing data as normal (score 0).

The total OASIS score ranges from 0 to 71.

Output a CSV file to `{output_path}` with these exact columns:
subject_id, hadm_id, stay_id, oasis, preiculos_score, age_score, gcs_score,
heart_rate_score, mbp_score, resp_rate_score, temp_score, urineoutput_score,
mechvent_score, electivesurgery_score

One row per ICU stay. The `oasis` column is the sum of the 10 component scores.
