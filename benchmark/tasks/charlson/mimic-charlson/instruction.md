# Task: Calculate Charlson Comorbidity Index

Calculate the Charlson Comorbidity Index (CCI) for each hospital
admission using ICD-9 and ICD-10 diagnosis codes
(Charlson et al., J Chronic Dis, 1987;
Quan et al., Med Care, 2005 for ICD coding algorithms).

Output a CSV file to `{output_path}` with these exact columns:
subject_id, hadm_id, age_score, myocardial_infarct, congestive_heart_failure, peripheral_vascular_disease, cerebrovascular_disease, dementia, chronic_pulmonary_disease, rheumatic_disease, peptic_ulcer_disease, mild_liver_disease, diabetes_without_cc, diabetes_with_cc, paraplegia, renal_disease, malignant_cancer, severe_liver_disease, metastatic_solid_tumor, aids, charlson_comorbidity_index

One row per hospital admission. All condition columns are 0 or 1.
Admissions with no diagnosis codes should have all flags = 0 and
charlson = age_score only.
