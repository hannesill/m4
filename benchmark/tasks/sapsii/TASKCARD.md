# SAPS-II -- Simplified Acute Physiology Score II

## What it is

SAPS-II is a severity scoring system (0-163) developed from a European/North American
multicenter study (Le Gall et al. 1993). It uses the worst physiological values from
the first 24 hours of ICU stay plus chronic disease status and admission type to predict
hospital mortality. Widely used for international ICU benchmarking.

## The 15 components

| Variable | Points | Scoring Logic |
|----------|--------|---------------|
| **Age** | 0-18 | 0 (<40) → 7 (40-59) → 12 (60-69) → 15 (70-74) → 16 (75-79) → 18 (>=80) |
| **Heart Rate** | 0-11 | 11 (<40) → 2 (40-69) → 0 (70-119) → 4 (120-159) → 7 (>=160) |
| **Systolic BP** | 0-13 | 13 (<70) → 5 (70-99) → 0 (100-199) → 2 (>=200) |
| **Temperature** | 0-3 | 0 (<39°C) → 3 (>=39°C) |
| **PaO2/FiO2** (if ventilated) | 0-11 | 11 (<100) → 9 (100-199) → 6 (>=200); 0 if not ventilated |
| **Urine Output** | 0-11 | 11 (<500 mL/day) → 4 (500-999) → 0 (>=1000) |
| **BUN** | 0-10 | 0 (<28 mg/dL) → 6 (28-83) → 10 (>=84) |
| **WBC** | 0-12 | 12 (<1 x10^9/L) → 0 (1-19) → 3 (>=20) |
| **Potassium** | 0-3 | 3 (<3 or >=5 mEq/L) → 0 (3-4.9) |
| **Sodium** | 0-5 | 5 (<125 mEq/L) → 0 (125-144) → 1 (>=145) |
| **Bicarbonate** | 0-6 | 6 (<15 mEq/L) → 3 (15-19) → 0 (>=20) |
| **Bilirubin** | 0-9 | 0 (<4 mg/dL) → 4 (4-5.9) → 9 (>=6) |
| **GCS** | 0-26 | 0 (14-15) → 5 (11-13) → 7 (9-10) → 13 (6-8) → 26 (<6) |
| **Chronic Disease** | 0-17 | 17 (AIDS) → 10 (Hematologic malignancy) → 9 (Metastatic cancer) → 0 (none) |
| **Admission Type** | 0-8 | 0 (Scheduled surgical) → 6 (Medical) → 8 (Unscheduled surgical) |

Total = sum of all 15 component scores. Missing data → score 0 (assumed normal).

## Data sources in MIMIC-IV

- **Age**: `age` derived table
- **Vitals (HR, SBP, Temp)**: `vitalsign` (time-series, windowed to 24h)
- **PaO2/FiO2**: `bg` (arterial only) + `ventilation` (InvasiveVent) + `chartevents` (CPAP/BiPAP detection via itemid 226732)
- **Urine Output**: `urine_output` (summed over 24h)
- **Labs (BUN, K, Na, HCO3)**: `chemistry`
- **WBC**: `complete_blood_count`
- **Bilirubin**: `enzyme`
- **GCS**: `gcs` (min value, GCS < 3 treated as null)
- **Comorbidity**: `diagnoses_icd` (ICD-9/10 codes for AIDS, hematologic malignancy, metastatic cancer)
- **Admission Type**: `admissions` (elective vs not) + `services` (surgical service flag)

## Why no 12h variant

SAPS-II was explicitly designed as a 24-hour assessment tool. The logistic regression
mortality formula was calibrated on 24h scores. A 12h variant would produce scores
with no validated mortality interpretation, and cumulative measures (urine output)
would be systematically biased. Unlike SOFA/SIRS which are organ dysfunction scores
applicable to any window, SAPS-II is a fixed-window prognostic score.

## Why standard vs raw

- **Standard**: derived measurement tables available (`vitalsign`, `chemistry`, `bg`, etc.)
- **Raw**: SAPS-II and task-relevant upstream derived tables are dropped,
  forcing aggregation from `chartevents`, `labevents`, and `outputevents`

Note: `diagnoses_icd`, `admissions`, and `services` are base hospital tables, NOT derived —
they remain available in raw mode.

## Subtleties to watch for

- **PaO2/FiO2 is only scored for ventilated patients** — those on invasive vent or
  CPAP/BiPAP. Non-ventilated patients get 0 points for this component (not NULL).
- **CPAP detection** uses `chartevents` itemid 226732 with regex matching for
  "cpap mask" or "bipap" — this is NOT from the `ventilation` derived table.
- **Admission type** requires joining `admissions` + `services`: elective admission
  with surgical service = scheduled surgical (0 pts), non-elective + surgical =
  unscheduled surgical (8 pts), all others = medical (6 pts).
- **Comorbidity priority**: AIDS (17) > Hematologic malignancy (10) > Metastatic
  cancer (9). Only the highest applicable score is used.
- **GCS < 3 treated as NULL** (erroneous data or tracheostomy artifact).
- The `mimiciv_derived.sapsii` table is always dropped (it's the answer).
