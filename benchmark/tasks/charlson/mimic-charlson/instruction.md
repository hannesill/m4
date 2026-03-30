# Task: Calculate Charlson Comorbidity Index

You have access to a MIMIC-IV clinical database (DuckDB) at `{db_path}`.
It contains hospital patient data with schemas `mimiciv_hosp`, `mimiciv_icu`,
and pre-computed intermediate tables in `mimiciv_derived`.

Calculate the Charlson Comorbidity Index (CCI) for each hospital admission
using ICD-9 and ICD-10 diagnosis codes from `mimiciv_hosp.diagnoses_icd`.

### 17 Comorbidity Conditions

Flag each condition as 1 (present) or 0 (absent) based on ICD codes:

| Condition | ICD-9 | ICD-10 |
|-----------|-------|--------|
| myocardial_infarct | 410.x, 412.x | I21.x, I22.x, I252 |
| congestive_heart_failure | 428.x, 39891, 40201, 40211, 40291, 40401, 40403, 40411, 40413, 40491, 40493, 4254-4259 | I43.x, I50.x, I099, I110, I130, I132, I255, I420, I425-I429, P290 |
| peripheral_vascular_disease | 440.x, 441.x, 0930, 4373, 4431-4439, 4471, 5571, 5579, V434 | I70.x, I71.x, I731, I738, I739, I771, I790, I792, K551, K558, K559, Z958, Z959 |
| cerebrovascular_disease | 430-438.x, 36234 | G45.x, G46.x, I60-I69.x, H340 |
| dementia | 290.x, 2941, 3312 | F00-F03.x, G30.x, F051, G311 |
| chronic_pulmonary_disease | 490-505.x, 4168, 4169, 5064, 5081, 5088 | J40-J47.x, J60-J67.x, I278, I279, J684, J701, J703 |
| rheumatic_disease | 725.x, 4465, 7100-7104, 7140-7142, 7148 | M05.x, M06.x, M32-M34.x, M315, M351, M353, M360 |
| peptic_ulcer_disease | 531-534.x | K25-K28.x |
| mild_liver_disease | 570-571.x, 0706, 0709, 5733, 5734, 5738, 5739, V427, 07022, 07023, 07032, 07033, 07044, 07054 | B18.x, K73.x, K74.x, K700-K703, K709, K713-K715, K717, K760, K762-K764, K768, K769, Z944 |
| diabetes_without_cc | 2500-2503, 2508, 2509 | E100, E101, E106, E108, E109, E110, E111, E116, E118, E119, E120, E121, E126, E128, E129, E130, E131, E136, E138, E139, E140, E141, E146, E148, E149 |
| diabetes_with_cc | 2504-2507 | E102-E105, E107, E112-E115, E117, E122-E125, E127, E132-E135, E137, E142-E145, E147 |
| paraplegia | 342.x, 343.x, 3341, 3440-3446, 3449 | G81.x, G82.x, G041, G114, G801, G802, G830-G834, G839 |
| renal_disease | 582.x, 585.x, 586.x, V56.x, 5830-5837, 5880, V420, V451, 40301, 40311, 40391, 40402, 40403, 40412, 40413, 40492, 40493 | N18.x, N19.x, I120, I131, N032-N037, N052-N057, N250, Z490-Z492, Z940, Z992 |
| malignant_cancer | 140-172.x, 1740-1958, 200-208.x, 2386 | C00-C26.x, C30-C34.x, C37-C41.x, C43.x, C45-C58.x, C60-C76.x, C81-C85.x, C88.x, C90-C97.x |
| severe_liver_disease | 4560-4562, 5722-5728 | I850, I859, I864, I982, K704, K711, K721, K729, K765-K767 |
| metastatic_solid_tumor | 196-199.x | C77-C80.x |
| aids | 042-044.x | B20-B22.x, B24.x |

ICD matching uses prefix matching: e.g., ICD-9 code '410' matches '4100', '4101',
etc. The `icd_version` column distinguishes ICD-9 (9) from ICD-10 (10).

### Weights and Hierarchy

| Weight | Conditions |
|--------|------------|
| 1 | MI, CHF, PVD, CVD, Dementia, COPD, Rheumatic, PUD, Mild liver, DM w/o CC |
| 2 | DM w/ CC, Paraplegia, Renal disease, Malignant cancer |
| 3 | Severe liver disease |
| 6 | Metastatic solid tumor, AIDS |

Hierarchy rules (higher overrides lower):
- Liver: `GREATEST(mild_liver_disease, 3 * severe_liver_disease)`
- Diabetes: `GREATEST(2 * diabetes_with_cc, diabetes_without_cc)`
- Cancer: `GREATEST(2 * malignant_cancer, 6 * metastatic_solid_tumor)`

### Age Score

From `mimiciv_derived.age`:

| Age | Points |
|-----|--------|
| <= 50 | 0 |
| 51-60 | 1 |
| 61-70 | 2 |
| 71-80 | 3 |
| > 80  | 4 |

### Total Score

`charlson_comorbidity_index` = age_score + weighted sum of conditions (with hierarchy rules)

Output a CSV file to `{output_path}` with these exact columns:
subject_id, hadm_id, age_score, myocardial_infarct, congestive_heart_failure, peripheral_vascular_disease, cerebrovascular_disease, dementia, chronic_pulmonary_disease, rheumatic_disease, peptic_ulcer_disease, mild_liver_disease, diabetes_without_cc, diabetes_with_cc, paraplegia, renal_disease, malignant_cancer, severe_liver_disease, metastatic_solid_tumor, aids, charlson_comorbidity_index

One row per hospital admission. All condition columns are 0 or 1. Admissions
with no diagnosis codes should have all flags = 0 and charlson = age_score only.
