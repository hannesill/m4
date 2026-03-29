# Task: Calculate LODS Score

You have access to a MIMIC-IV clinical database (DuckDB) at `{db_path}`.
It contains ICU patient data with schemas `mimiciv_hosp`, `mimiciv_icu`,
and pre-computed intermediate tables in `mimiciv_derived`.

Calculate the Logistic Organ Dysfunction Score (LODS) for each ICU stay
using data from the first 24 hours of ICU admission.

LODS scores organ dysfunction across 6 systems:

| System | Variables | 0 | 1 | 3 | 5 |
|--------|-----------|---|---|---|---|
| Neurologic | GCS | 14-15 | 9-13 | 6-8 | <=5 |
| Cardiovascular | HR, SBP | Normal | HR>=140 or SBP 90-239 | SBP<70 or SBP>=270 | HR<30 or SBP<40 |
| Renal | BUN, Creatinine, UO | Normal | Cr>=1.2 or BUN>=7.5 mg/dL | Cr>=1.6 or UO<750 or BUN>=28 or UO>=10000 mL | UO<500 or BUN>=56 |
| Pulmonary | PaO2/FiO2 (ventilated) | Not ventilated | PF>=150 | PF<150 | — |
| Hematologic | WBC, Platelets | Normal | WBC<2.5 or Plt<50 or WBC>=50 x10^9/L | WBC<1.0 | — |
| Hepatic | PT, Bilirubin | Normal | Bili>=2.0 mg/dL or PT>15s or PT<3s | — | — |

The pulmonary component is only scored for patients on mechanical ventilation
or CPAP/BiPAP. Non-ventilated patients receive 0 for this component.

The total LODS score ranges from 0 to 22. Treat missing data as normal (score 0).

Output a CSV file to `{output_path}` with these exact columns:
subject_id, hadm_id, stay_id, lods, neurologic, cardiovascular, renal,
pulmonary, hematologic, hepatic

One row per ICU stay. The `lods` column is the sum of the six component scores.
