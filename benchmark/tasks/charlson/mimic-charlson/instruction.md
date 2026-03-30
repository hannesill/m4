# Task: Calculate Charlson Comorbidity Index

You have access to a MIMIC-IV clinical database (DuckDB) at `{db_path}`.
It contains hospital patient data with schemas `mimiciv_hosp`, `mimiciv_icu`,
and pre-computed intermediate tables in `mimiciv_derived`.

Calculate the Charlson Comorbidity Index (CCI) for each hospital admission
using ICD-9 and ICD-10 diagnosis codes (Charlson et al., J Chronic Dis, 1987).
Use the Quan 2005 ICD-9-CM and ICD-10-CM coding algorithms to map diagnoses
to the 17 comorbidity conditions (Quan et al., Med Care, 2005). ICD codes
are matched using prefix matching (e.g., ICD-9 code '410' matches '4100',
'4101', etc.).

### 17 Comorbidity Conditions and Weights

| Weight | Conditions |
|--------|------------|
| 1 | Myocardial infarct, CHF, Peripheral vascular disease, Cerebrovascular disease, Dementia, Chronic pulmonary disease, Rheumatic disease, Peptic ulcer disease, Mild liver disease, Diabetes without chronic complications |
| 2 | Diabetes with chronic complications, Paraplegia, Renal disease, Malignant cancer (non-metastatic) |
| 3 | Severe liver disease |
| 6 | Metastatic solid tumor, AIDS/HIV |

Flag each condition as 1 (present) or 0 (absent).

### Hierarchy Rules

When both mild and severe forms of a condition are present, the higher-weighted
form takes precedence in the total score:
- Liver: severe (weight 3) overrides mild (weight 1)
- Diabetes: with complications (weight 2) overrides without (weight 1)
- Cancer: metastatic (weight 6) overrides non-metastatic (weight 2)

### Age Score

| Age | Points |
|-----|--------|
| <= 50 | 0 |
| 51-60 | 1 |
| 61-70 | 2 |
| 71-80 | 3 |
| > 80  | 4 |

### Total Score

`charlson_comorbidity_index` = age_score + weighted sum of conditions (with hierarchy rules applied)

Output a CSV file to `{output_path}` with these exact columns:
subject_id, hadm_id, age_score, myocardial_infarct, congestive_heart_failure, peripheral_vascular_disease, cerebrovascular_disease, dementia, chronic_pulmonary_disease, rheumatic_disease, peptic_ulcer_disease, mild_liver_disease, diabetes_without_cc, diabetes_with_cc, paraplegia, renal_disease, malignant_cancer, severe_liver_disease, metastatic_solid_tumor, aids, charlson_comorbidity_index

One row per hospital admission. All condition columns are 0 or 1. Admissions
with no diagnosis codes should have all flags = 0 and charlson = age_score only.
