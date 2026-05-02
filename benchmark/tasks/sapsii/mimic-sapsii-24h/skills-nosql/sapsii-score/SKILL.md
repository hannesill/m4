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

| Variable | Scoring Range | Points |
|----------|---------------|--------|
| Age | <40 to >=80 | 0-18 |
| Heart Rate | <40 to >=160 | 0-11 |
| Systolic BP | <70 to >=200 | 0-13 |
| Temperature | <39 or >=39C | 0-3 |
| PaO2/FiO2 (if ventilated) | <100 to >=200 | 6-11 |
| Urine Output | <500 to >=1000 mL/day | 0-11 |
| BUN | <28 to >=84 mg/dL | 0-10 |
| WBC | <1 to >=20 x10^9/L | 0-12 |
| Potassium | <3 or >=5 mEq/L | 0-3 |
| Sodium | <125 or >=145 mEq/L | 0-5 |
| Bicarbonate | <15 to >=20 mEq/L | 0-6 |
| Bilirubin | <4 to >=6 mg/dL | 0-9 |
| GCS | <6 to >=14 | 0-26 |
| Chronic Disease | AIDS/Hematologic Malignancy/Metastatic Cancer | 9-17 |
| Admission Type | Scheduled Surgical/Medical/Unscheduled Surgical | 0-8 |

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
