WITH
patient_cohort AS (
SELECT
p.subject_id,
a.hadm_id,
a.admittime,
a.dischtime,
a.hospital_expire_flag,
(p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission
FROM
`physionet-data.mimiciv_3_1_hosp.patients` AS p
JOIN
`physionet-data.mimiciv_3_1_hosp.admissions` AS a
ON p.subject_id = a.subject_id
WHERE
p.gender = 'M'
AND a.admittime IS NOT NULL
AND a.dischtime IS NOT NULL
),
heart_failure_admissions AS (
SELECT DISTINCT
pc.hadm_id,
pc.admittime,
pc.dischtime,
pc.hospital_expire_flag
FROM
patient_cohort AS pc
JOIN
`physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
ON pc.hadm_id = d.hadm_id
WHERE
pc.age_at_admission BETWEEN 38 AND 48
AND (
d.icd_code LIKE 'I50%'
OR d.icd_code LIKE '428%'
)
),
comorbidity_counts AS (
SELECT
hadm_id,
COUNT(DISTINCT icd_code) AS num_comorbidities
FROM
`physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
GROUP BY
hadm_id
),
stratified_patients AS (
SELECT
hfa.hadm_id,
hfa.hospital_expire_flag,
cc.num_comorbidities,
CASE
WHEN EXISTS (
SELECT
1
FROM
`physionet-data.mimiciv_3_1_icu.icustays` AS icu
WHERE
icu.hadm_id = hfa.hadm_id
)
THEN 'Higher Severity (ICU)'
ELSE 'Lower Severity (No ICU)'
END AS severity_level,
CASE
WHEN DATETIME_DIFF(hfa.dischtime, hfa.admittime, DAY) BETWEEN 1 AND 3
THEN '1-3 days'
WHEN DATETIME_DIFF(hfa.dischtime, hfa.admittime, DAY) BETWEEN 4 AND 7
THEN '4-7 days'
WHEN DATETIME_DIFF(hfa.dischtime, hfa.admittime, DAY) >= 8
THEN '>=8 days'
END AS los_category,
CASE
WHEN ch.charlson_comorbidity_index <= 3
THEN '<=3'
WHEN ch.charlson_comorbidity_index BETWEEN 4 AND 5
THEN '4-5'
WHEN ch.charlson_comorbidity_index > 5
THEN '>5'
ELSE 'Unknown'
END AS charlson_category
FROM
heart_failure_admissions AS hfa
LEFT JOIN
`physionet-data.mimiciv_3_1_derived.charlson` AS ch
ON hfa.hadm_id = ch.hadm_id
LEFT JOIN
comorbidity_counts AS cc
ON hfa.hadm_id = cc.hadm_id
WHERE
DATETIME_DIFF(hfa.dischtime, hfa.admittime, DAY) >= 1
),
final_aggregation AS (
SELECT
severity_level,
los_category,
charlson_category,
COUNT(*) AS total_admissions,
SUM(hospital_expire_flag) AS total_deaths,
AVG(num_comorbidities) AS avg_comorbidity_count
FROM
stratified_patients
GROUP BY
severity_level,
los_category,
charlson_category
)
SELECT
severity_level,
los_category,
charlson_category,
total_admissions,
total_deaths,
ROUND(avg_comorbidity_count, 1) AS avg_comorbidity_count,
ROUND((total_deaths * 100.0) / total_admissions, 2) AS mortality_rate_percent,
ROUND(
100 * (
(
total_deaths + 0.5 * POWER(1.96, 2)
) / (
total_admissions + POWER(1.96, 2)
) - 1.96 * SQRT(
(
total_deaths * (total_admissions - total_deaths) / total_admissions + 0.25 * POWER(1.96, 2)
)
) / (
total_admissions + POWER(1.96, 2)
)
),
2
) AS ci_95_lower,
ROUND(
100 * (
(
total_deaths + 0.5 * POWER(1.96, 2)
) / (
total_admissions + POWER(1.96, 2)
) + 1.96 * SQRT(
(
total_deaths * (total_admissions - total_deaths) / total_admissions + 0.25 * POWER(1.96, 2)
)
) / (
total_admissions + POWER(1.96, 2)
)
),
2
) AS ci_95_upper
FROM
final_aggregation
WHERE
total_admissions > 0
ORDER BY
severity_level DESC,
CASE
WHEN los_category = '1-3 days'
THEN 1
WHEN los_category = '4-7 days'
THEN 2
WHEN los_category = '>=8 days'
THEN 3
END,
CASE
WHEN charlson_category = '<=3'
THEN 1
WHEN charlson_category = '4-5'
THEN 2
WHEN charlson_category = '>5'
THEN 3
ELSE 4
END;
