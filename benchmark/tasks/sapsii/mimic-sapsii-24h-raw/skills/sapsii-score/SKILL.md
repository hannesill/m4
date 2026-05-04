---
name: sapsii-score
description: Calculate SAPS-II (Simplified Acute Physiology Score II) for ICU patients. Use for mortality prediction, severity assessment, or international ICU benchmarking.
tier: validated
category: clinical
---

# SAPS-II Score Calculation

The Simplified Acute Physiology Score II (SAPS-II) is a severity scoring system developed from a European/North American multicenter study. Calculated from the worst values in the first 24 hours of ICU stay.

## M4Bench Use

In M4Bench, target concept tables listed in the task configuration are removed or unavailable in the agent database. Use this skill as procedural guidance and derive the requested output from available source or intermediate tables; do not rely on a precomputed target table or bundled SQL script.

## When to Use This Skill

- Hospital mortality prediction
- Severity stratification
- International benchmarking (widely used in European ICUs)
- Research cohort matching
- Quality improvement initiatives

## Score Components (First 24 Hours)

Use the worst value in the first 24 hours of ICU admission. When both low and
high extremes can score, assign the score for the qualifying extreme with the
highest SAPS-II point value. Missing components are scored as 0 in M4Bench.

| Component | Value | Points |
|-----------|-------|--------|
| Age, years | < 40 | 0 |
| Age, years | 40-59 | 7 |
| Age, years | 60-69 | 12 |
| Age, years | 70-74 | 15 |
| Age, years | 75-79 | 16 |
| Age, years | >= 80 | 18 |
| Heart rate, bpm | < 40 | 11 |
| Heart rate, bpm | 40-69 | 2 |
| Heart rate, bpm | 70-119 | 0 |
| Heart rate, bpm | 120-159 | 4 |
| Heart rate, bpm | >= 160 | 7 |
| Systolic BP, mmHg | < 70 | 13 |
| Systolic BP, mmHg | 70-99 | 5 |
| Systolic BP, mmHg | 100-199 | 0 |
| Systolic BP, mmHg | >= 200 | 2 |
| Temperature, deg C | < 39.0 | 0 |
| Temperature, deg C | >= 39.0 | 3 |
| PaO2/FiO2, if ventilated or CPAP/BiPAP | < 100 | 11 |
| PaO2/FiO2, if ventilated or CPAP/BiPAP | 100-199 | 9 |
| PaO2/FiO2, if ventilated or CPAP/BiPAP | >= 200 | 6 |
| PaO2/FiO2, not ventilated/CPAP/BiPAP | Any value or missing | 0 |
| Urine output, mL/day | < 500 | 11 |
| Urine output, mL/day | 500-999 | 4 |
| Urine output, mL/day | >= 1000 | 0 |
| BUN, mg/dL | < 28 | 0 |
| BUN, mg/dL | 28-83 | 6 |
| BUN, mg/dL | >= 84 | 10 |
| WBC, x10^9/L | < 1.0 | 12 |
| WBC, x10^9/L | 1.0-19.9 | 0 |
| WBC, x10^9/L | >= 20.0 | 3 |
| Potassium, mEq/L | < 3.0 | 3 |
| Potassium, mEq/L | 3.0-4.9 | 0 |
| Potassium, mEq/L | >= 5.0 | 3 |
| Sodium, mEq/L | < 125 | 5 |
| Sodium, mEq/L | 125-144 | 0 |
| Sodium, mEq/L | >= 145 | 1 |
| Bicarbonate, mEq/L | < 15 | 6 |
| Bicarbonate, mEq/L | 15-19 | 3 |
| Bicarbonate, mEq/L | >= 20 | 0 |
| Bilirubin, mg/dL | < 4.0 | 0 |
| Bilirubin, mg/dL | 4.0-5.9 | 4 |
| Bilirubin, mg/dL | >= 6.0 | 9 |
| GCS | < 3 | Treat as missing |
| GCS | 3-5 | 26 |
| GCS | 6-8 | 13 |
| GCS | 9-10 | 7 |
| GCS | 11-13 | 5 |
| GCS | 14-15 | 0 |
| Chronic disease | AIDS | 17 |
| Chronic disease | Hematologic malignancy | 10 |
| Chronic disease | Metastatic cancer | 9 |
| Chronic disease | None of the above | 0 |
| Admission type | Scheduled surgical | 0 |
| Admission type | Medical | 6 |
| Admission type | Unscheduled surgical | 8 |

## Critical Implementation Notes

1. **PaO2/FiO2 Scoring**: Only scored for patients on mechanical ventilation OR CPAP/BiPAP. Non-ventilated patients get 0 points for this component.

2. **Mortality Probability**: Calculated using:
   ```
   sapsii_prob = 1 / (1 + exp(-(-7.7631 + 0.0737*sapsii + 0.9971*ln(sapsii+1))))
   ```
   This 1993 formula tends to overestimate mortality in modern ICU cohorts (calibration drift). Consider recalibration for contemporary populations.

3. **Time Window**: Uses worst value from ICU admission to 24 hours after.

## Dataset-Specific Implementation Notes

### MIMIC-IV

**MIMIC-IV implementation details:**
- **Comorbidity Definitions** (ICD-based):
  - **AIDS**: ICD-9 042-044, ICD-10 B20-B22, B24
  - **Hematologic Malignancy**: ICD-9 200xx-208xx, ICD-10 C81-C96
  - **Metastatic Cancer**: ICD-9 196x-199x, ICD-10 C77-C79, C800
- **Admission Type**: Classified using `admissions.admission_type` (elective vs not) + surgical service flag from `services` table.
- **GCS Handling**: GCS < 3 is treated as null (erroneous or tracheostomy). Sedated patients use pre-sedation GCS.

**MIMIC-IV limitations:**
- Urine output is summed over available hours, not extrapolated to 24h. For stays <24h, this may overestimate severity.
- Follow the MIT-LCP/mimic-code canonical component definitions.

### eICU

For eICU, SAPS-II must be calculated from raw tables. 13 of 15 components are straightforward:

| Component | eICU Source |
|-----------|-------------|
| Age | `patient.age` (string; "> 89" for elderly) |
| Heart Rate, Systolic BP, Temperature | `vitalperiodic` / `vitalaperiodic` |
| PaO2, FiO2 | `lab` |
| Ventilation status | `respiratorycare` / `respiratorycharting` |
| Urine Output | `intakeoutput` |
| BUN, WBC, K, Na, HCO3, Bilirubin | `lab` (text `labname`, not numeric itemid) |
| GCS | `nursecharting` |

**eICU limitations:**
- **Comorbidities**: The `diagnosis` table uses free-text `diagnosisstring` with variably populated `icd9code` across the 208 sites. ICD-based extraction (AIDS, hematologic malignancy, metastatic cancer) may have incomplete capture. Consider supplementing with `pasthistory` table or text matching on `diagnosisstring`.
- **Admission type**: No direct elective/surgical classification as in MIMIC. Must approximate from `patient.unitadmitsource` and service fields.
- **Ventilation detection**: Different logic than MIMIC — uses `respiratorycare` and `respiratorycharting` tables rather than procedural events.


## References

- Le Gall JR, Lemeshow S, Saulnier F. "A new Simplified Acute Physiology Score (SAPS II) based on a European/North American multicenter study." JAMA. 1993;270(24):2957-2963.
