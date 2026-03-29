---
name: sapsii-score
description: Calculate SAPS-II (Simplified Acute Physiology Score II) for ICU patients. Use for mortality prediction, severity assessment, or international ICU benchmarking.
tier: validated
category: clinical
---

# SAPS-II Score Calculation

The Simplified Acute Physiology Score II (SAPS-II) is a severity scoring system developed from a European/North American multicenter study. Calculated from the worst values in the first 24 hours of ICU stay.

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

## Dataset Availability

### MIMIC-IV

SAPS-II is available as a pre-computed derived table. Materialize with:

```bash
m4 init-derived mimic-iv          # All derived tables including sapsii
```

The derived table provides the total score, predicted mortality probability, and all 15 component sub-scores (`age_score`, `hr_score`, `sysbp_score`, `temp_score`, `pao2fio2_score`, `uo_score`, `bun_score`, `wbc_score`, `potassium_score`, `sodium_score`, `bicarbonate_score`, `bilirubin_score`, `gcs_score`, `comorbidity_score`, `admissiontype_score`).

BigQuery users already have this table via `physionet-data.mimiciv_derived.sapsii` without running `init-derived`.

**MIMIC-IV implementation details:**
- **Comorbidity Definitions** (ICD-based):
  - **AIDS**: ICD-9 042-044, ICD-10 B20-B22, B24
  - **Hematologic Malignancy**: ICD-9 200xx-208xx, ICD-10 C81-C96
  - **Metastatic Cancer**: ICD-9 196x-199x, ICD-10 C77-C79, C800
- **Admission Type**: Classified using `admissions.admission_type` (elective vs not) + surgical service flag from `services` table.
- **GCS Handling**: GCS < 3 is treated as null (erroneous or tracheostomy). Sedated patients use pre-sedation GCS.

**MIMIC-IV limitations:**
- Urine output is summed over available hours, not extrapolated to 24h. For stays <24h, this may overestimate severity.
- Follows MIT-LCP/mimic-code canonical implementation.

### eICU

SAPS-II is **not pre-computed** in eICU (only APACHE IV is provided in `apachepatientresult`). It must be calculated from raw tables. 13 of 15 components are straightforward:

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

See `scripts/mimic-iv.sql` for the full MIMIC-IV implementation. An eICU script is not yet available.

## Example: Severity Distribution

```sql
SELECT
    CASE
        WHEN sapsii < 25 THEN 'Low (<25)'
        WHEN sapsii < 50 THEN 'Moderate (25-49)'
        WHEN sapsii < 75 THEN 'High (50-74)'
        ELSE 'Very High (>=75)'
    END AS severity_category,
    COUNT(*) AS n_patients,
    ROUND(AVG(sapsii_prob), 3) AS avg_predicted_mortality
FROM mimiciv_derived.sapsii
GROUP BY 1
ORDER BY 1;
```

## Example: Component Analysis

```sql
-- Which components contribute most to high SAPS-II?
SELECT
    'Age' AS component, AVG(age_score) AS avg_score FROM mimiciv_derived.sapsii WHERE sapsii >= 50
UNION ALL
SELECT 'Heart Rate', AVG(hr_score) FROM mimiciv_derived.sapsii WHERE sapsii >= 50
UNION ALL
SELECT 'Systolic BP', AVG(sysbp_score) FROM mimiciv_derived.sapsii WHERE sapsii >= 50
UNION ALL
SELECT 'GCS', AVG(gcs_score) FROM mimiciv_derived.sapsii WHERE sapsii >= 50
UNION ALL
SELECT 'Comorbidity', AVG(comorbidity_score) FROM mimiciv_derived.sapsii WHERE sapsii >= 50
ORDER BY avg_score DESC;
```

## References

- Le Gall JR, Lemeshow S, Saulnier F. "A new Simplified Acute Physiology Score (SAPS II) based on a European/North American multicenter study." JAMA. 1993;270(24):2957-2963.
