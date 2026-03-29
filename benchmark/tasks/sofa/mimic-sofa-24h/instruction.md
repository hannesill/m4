# Task: Calculate SOFA Score

You have access to a MIMIC-IV clinical database (DuckDB) at `{db_path}`.
It contains ICU patient data with schemas `mimiciv_hosp`, `mimiciv_icu`,
and pre-computed intermediate tables in `mimiciv_derived`.

Calculate the Sequential Organ Failure Assessment (SOFA) score for each
ICU stay using data from the first 24 hours (from 6 hours before ICU
admission to 24 hours after admission).

SOFA scores organ dysfunction across 6 systems, each scored 0-4:

| System | 0 | 1 | 2 | 3 | 4 |
|--------|---|---|---|---|---|
| Respiration (PaO2/FiO2 mmHg) | >= 400 | < 400 | < 300 | < 200 + respiratory support | < 100 + respiratory support |
| Coagulation (Platelets x10^3/uL) | >= 150 | < 150 | < 100 | < 50 | < 20 |
| Liver (Bilirubin mg/dL) | < 1.2 | 1.2-1.9 | 2.0-5.9 | 6.0-11.9 | >= 12.0 |
| Cardiovascular | MAP >= 70 | MAP < 70 | Dopa <= 5 or Dobutamine any dose | Dopa > 5 or Epi <= 0.1 or Norepi <= 0.1 | Dopa > 15 or Epi > 0.1 or Norepi > 0.1 |
| CNS (GCS) | 15 | 13-14 | 10-12 | 6-9 | < 6 |
| Renal (Creatinine mg/dL or UO mL/day) | < 1.2 | 1.2-1.9 | 2.0-3.4 | 3.5-4.9 or UO < 500 | >= 5.0 or UO < 200 |

Vasopressor doses are in mcg/kg/min. Respiratory support means invasive
mechanical ventilation. Use only arterial blood gas specimens for PaO2/FiO2.

The total SOFA score ranges from 0 to 24. Treat missing data as normal (score 0).

Output a CSV file to `{output_path}` with these exact columns:
subject_id, hadm_id, stay_id, sofa, respiration, coagulation, liver, cardiovascular, cns, renal

One row per ICU stay. The `sofa` column is the sum of the six component scores.
