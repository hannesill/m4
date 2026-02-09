---
name: apache-iv-score
description: Calculate APACHE IV (Acute Physiology and Chronic Health Evaluation IV) score for ICU mortality prediction. Use for severity assessment, hospital mortality prediction, ICU benchmarking, or case-mix adjustment. eICU has pre-computed scores; MIMIC-IV requires custom implementation with diagnosis mapping challenges.
tier: expert
category: clinical
---

# APACHE IV Score Calculation

APACHE IV predicts hospital mortality for ICU patients using acute physiology, age, chronic health conditions, and diagnosis. Published in 2006 with 110,558 patients from 104 U.S. ICUs. The model has excellent discrimination (AUC-ROC = 0.88) and calibration (Hosmer-Lemeshow p = .08).

## When to Use This Skill

- User asks about APACHE IV score calculation
- Hospital mortality prediction for ICU patients
- ICU performance benchmarking (SMR calculation)
- Case-mix adjustment for quality comparison
- Severity stratification for research cohorts

## Components and Explanatory Power

| Component | Explanatory Power | Description |
|-----------|------------------|-------------|
| **Acute Physiology (APS)** | 65.8% | 16 physiological variables (worst in first 24h) + GCS adjustment + PaO2/FiO2 |
| **Diagnosis** | 16.5% | 116 diagnostic categories + emergency surgery + thrombolytic therapy (AMI) |
| **Age** | 9.4% | Continuous with 5 spline terms (knots at 27, 51, 64, 74, 86 years) |
| **Chronic Health** | 5.0% | 7 conditions: AIDS, cirrhosis, hepatic failure, immunosuppression, lymphoma, leukemia/myeloma, metastatic cancer |
| **Admission Variables** | 2.9% | Admission source + prior length of stay (with spline terms) |
| **Mechanical Ventilation** | 0.6% | Binary flag for ventilation on ICU day 1 |

## Acute Physiology Variables

| Variable | Units | Notes |
|----------|-------|-------|
| Heart rate | bpm | Highest or lowest deviation from normal |
| Mean arterial pressure | mmHg | Lowest value |
| Temperature | °C | Highest or lowest deviation from normal |
| Respiratory rate | breaths/min | Highest or lowest deviation from normal |
| PaO2/FiO2 ratio | mmHg | Worst oxygenation (arterial specimens only) |
| Hematocrit | % | Lowest value |
| WBC | ×10³/μL | Highest or lowest deviation from normal |
| Creatinine | mg/dL | Highest value |
| Urine output | mL/24h | Total volume in first 24 hours |
| BUN | mg/dL | Highest value |
| Sodium | mEq/L | Highest or lowest deviation from normal |
| Albumin | g/dL | Lowest value |
| Bilirubin | mg/dL | Highest value |
| Glucose | mg/dL | Highest or lowest deviation from normal |
| pH | - | Lowest value (arterial specimens only) |
| Glasgow Coma Scale | 3-15 | Lowest value (use pre-sedation if sedated) |

## Required Tables (eICU)

For pre-computed APACHE IV scores:
- `eicu_crd.apachepatientresult` - Pre-computed scores and predictions
- `eicu_crd.apacheapsvar` - Input physiology variables (for reference)
- `eicu_crd.apachepredvar` - Demographics and mapped diagnosis categories
- `eicu_crd.patient` - Patient outcomes and demographics

See also [references/eicu.md](eicu.md) for pre-computed score usage and related tables.

## Critical Implementation Notes

### MIMIC-IV: No SQL Code Provided

**This skill does not provide complete APACHE IV calculation SQL for MIMIC-IV.** Full implementation is technically possible but impractical for most use cases.

**Reasons:**
- **Diagnosis Mapping**: 430 ICU admission diagnoses must be mapped to 116 APACHE IV categories. No standard ICD-9/10 to APACHE IV mapping exists, and creating one requires substantial clinical expertise and validation.
- **Chronic Health Extraction**: 7 chronic conditions must be accurately extracted from ICD codes with careful attention to coding practices. Some of them (e.g. NYHA Class IV heart failure) are also hard to approximate with ICD codes.
- **Spline Calculations**: Age, APS, and prior LOS require restricted cubic spline transformations that are complex to implement correctly in SQL.

**Recommended Alternatives for MIMIC-IV:**
- `mimiciv_derived.sofa` - SOFA score (hourly, pre-computed)
- `mimiciv_derived.sapsii` - SAPS II score (pre-computed)
- `mimiciv_derived.oasis` - OASIS score (pre-computed)
- `mimiciv_derived.lods` - LODS score (pre-computed)

Use APACHE IV only if diagnosis-specific mortality prediction is essential AND you can create reliable diagnosis mapping.

### eICU: Use Pre-computed Scores

eICU provides pre-computed APACHE IV/IVa scores in `apachepatientresult`. Diagnosis mapping is already performed (`apachepredvar.admitdiagnosis`). **Always use these pre-computed scores instead of manual calculation.**

### General Notes

1. **Time Window**: Use worst value within the first 24 hours of ICU admission. This is a fixed window from admission, NOT a rolling window like SOFA.

2. **Coefficients Are Published**: All coefficients are available in the original paper (Table 6 for splines, Appendix Tables 1-3 for diagnosis and other variables)

3. **GCS in Sedated Patients**: Use pre-sedation GCS when possible. If unable to assess due to sedation/paralysis, a separate "unable to assess" variable (coefficient = 0.7858, OR = 2.19) is used instead of defaulting to normal. Additionally, a rescaled GCS variable (15 − measured GCS) with coefficient 0.0391 is applied.

4. **Arterial Blood Gas**: Use only arterial specimens (`specimen = 'ART.'` in labevents) for PaO2, pH, and PaCO2.

5. **Reference Patient**: The default category (coefficient = 0) is: diagnosis "AMI other", no emergency surgery, direct/ER/stepdown admission, no chronic health items, APS = 0, GCS = 15, not ventilated, not receiving thrombolytics.

6. **Exclusion Criteria**: The original study excluded: age < 16, ICU stay < 4h or > 365 days, burns, most transplants (except hepatic/renal), transfers from another ICU, and repeat ICU admissions (only first ICU admission per hospitalization).

7. **Model Calibration Over Time**: APACHE IV was developed on 2002-2003 data. The original paper demonstrates that older APACHE III versions systematically overestimated mortality when applied to newer data. Consider recalibration for contemporary cohorts.

8. **Missing Data**: Unlike SOFA where missing components are imputed as 0, APACHE IV uses the APS scoring system where missing values may have different implications. Document which components are missing and consider appropriate imputation methods.

## Example Queries

### Pre-computed APACHE IV Scores (eICU)

eICU provides pre-computed APACHE IV/IVa scores:

```sql
SELECT
    patientunitstayid,
    apacheversion,                  -- 'IV' or 'IVa'
    apachescore,                    -- Acute physiology score
    predictedhospitalmortality,     -- Predicted mortality (0-1)
    predictediculos,                -- Predicted ICU length of stay
    actualhospitalmortality         -- Actual outcome (ALIVE/EXPIRED)
FROM eicu_crd.apachePatientResult
WHERE apacheversion = 'IVa';
```

Note: MIMIC-IV does not have a pre-computed APACHE IV table. Use `mimiciv_derived.sapsii` or `mimiciv_derived.sofa` for simpler severity scores.

### SMR Calculation (eICU)

SMR (Standardized Mortality Ratio) = Observed Deaths / Expected Deaths. Values > 1.0 indicate higher-than-predicted mortality; < 1.0 indicate lower-than-predicted mortality.

```sql
WITH mortality_data AS (
    SELECT
        a.patientunitstayid,
        a.predictedhospitalmortality,
        CASE WHEN p.hospitaldischargestatus = 'Expired' THEN 1 ELSE 0 END AS died
    FROM eicu_crd.apachePatientResult a
    JOIN eicu_crd.patient p
        ON a.patientunitstayid = p.patientunitstayid
    WHERE a.apacheversion = 'IVa'
      AND a.predictedhospitalmortality IS NOT NULL
)
SELECT
    COUNT(*) AS n_patients,
    SUM(died) AS observed_deaths,
    ROUND(SUM(predictedhospitalmortality), 1) AS expected_deaths,
    ROUND(SUM(died) / NULLIF(SUM(predictedhospitalmortality), 0), 2) AS SMR
FROM mortality_data;
```

### Calibration by Score Decile (eICU)

```sql
WITH apache_data AS (
    SELECT
        a.apachescore,
        a.predictedhospitalmortality,
        CASE WHEN p.hospitaldischargestatus = 'Expired' THEN 1 ELSE 0 END AS died
    FROM eicu_crd.apachePatientResult a
    JOIN eicu_crd.patient p
        ON a.patientunitstayid = p.patientunitstayid
    WHERE a.apacheversion = 'IVa'
)
SELECT
    FLOOR(apachescore / 10) * 10 AS score_decile,
    COUNT(*) AS n,
    ROUND(AVG(predictedhospitalmortality), 3) AS predicted_mortality,
    ROUND(AVG(died), 3) AS observed_mortality
FROM apache_data
GROUP BY FLOOR(apachescore / 10) * 10
ORDER BY score_decile;
```

## References

- Zimmerman JE, Kramer AA, McNair DS, Malila FM. Acute Physiology and Chronic Health Evaluation (APACHE) IV: hospital mortality assessment for today's critically ill patients. Crit Care Med. 2006;34(5):1297-1310. doi:10.1097/01.CCM.0000215112.84523.F0
- Knaus WA, Wagner DP, Draper EA, et al. The APACHE III prognostic system. Risk prediction of hospital mortality for critically ill hospitalized adults. Chest. 1991;100(6):1619-1636.
