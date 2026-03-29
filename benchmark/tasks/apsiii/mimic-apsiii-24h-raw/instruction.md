# Task: Calculate APS III (APACHE III) Score (Raw Tables)

You have access to a MIMIC-IV clinical database (DuckDB) at `{db_path}`.
It contains ICU patient data with schemas `mimiciv_hosp` and `mimiciv_icu`.

Calculate the Acute Physiology Score III (APS III) for each ICU stay
using the worst values from the first 24 hours of ICU admission. Compute
directly from the raw `chartevents`, `labevents`, and `outputevents`
tables.

APS III scores 16 physiological variables. Most variables use the value
**furthest from a physiological reference** (not simply min or max):

| Component | Reference | Points | Scoring |
|-----------|-----------|--------|---------|
| Heart Rate | 75 bpm | 0-17 | Furthest from 75 |
| Mean BP | 90 mmHg | 0-23 | Furthest from 90 |
| Temperature | 38°C | 0-20 | Furthest from 38 |
| Respiratory Rate | 19/min | 0-18 | Furthest from 19; if ventilated and RR<14, score=0 |
| PaO2 or A-aDO2 | — | 0-15 | Use PaO2 if non-ventilated and FiO2<50%; use A-aDO2 if ventilated and FiO2>=50% |
| Hematocrit | 45.5% | 0-3 | Furthest from 45.5 |
| WBC | 11.5 x10^9/L | 0-19 | Furthest from 11.5 |
| Creatinine | 1.0 mg/dL | 0-10 | Furthest from 1; modified if acute renal failure |
| Urine Output | — | 0-15 | 24h total (mL) |
| BUN | — | 0-12 | Always max |
| Sodium | 145.5 mEq/L | 0-4 | Furthest from 145.5 |
| Albumin | 3.5 g/dL | 0-11 | Furthest from 3.5 |
| Bilirubin | — | 0-16 | Always max |
| Glucose | 130 mg/dL | 0-9 | Furthest from 130 |
| Acid-Base | — | 0-12 | 2D matrix of pH × PaCO2 |
| GCS | — | 0-48 | 3D matrix of Eyes × Verbal × Motor |

Use only arterial blood gas specimens. Acute renal failure (ARF) is
defined as creatinine >= 1.5, urine output < 410 mL/day, and no
chronic kidney disease stages 4-6. If intubated (GCS unable), GCS
score = 0.

The total APS III score ranges from 0 to 299. Treat missing data as
normal (score 0).

Output a CSV file to `{output_path}` with these exact columns:
subject_id, hadm_id, stay_id, apsiii, hr_score, mbp_score, temp_score,
resp_rate_score, pao2_aado2_score, hematocrit_score, wbc_score,
creatinine_score, uo_score, bun_score, sodium_score, albumin_score,
bilirubin_score, glucose_score, acidbase_score, gcs_score

One row per ICU stay. The `apsiii` column is the sum of the 16
component scores.
