WITH
base_admissions AS (
  SELECT
    p.subject_id,
    a.hadm_id,
    a.admittime,
    a.dischtime,
    a.hospital_expire_flag,
    (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission,
    DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay
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
postop_admissions AS (
  SELECT
    b.hadm_id,
    b.hospital_expire_flag,
    b.length_of_stay
  FROM
    base_admissions AS b
  WHERE
    b.age_at_admission BETWEEN 60 AND 70
    AND EXISTS (
      SELECT 1
      FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
      WHERE d.hadm_id = b.hadm_id
      AND (
        (d.icd_version = 9 AND SUBSTR(d.icd_code, 1, 3) IN ('996', '997', '998', '999'))
        OR (d.icd_version = 10 AND SUBSTR(d.icd_code, 1, 3) BETWEEN 'T80' AND 'T88')
      )
    )
),
cohort_with_scores AS (
  SELECT
    pa.hadm_id,
    pa.hospital_expire_flag,
    pa.length_of_stay,
    ch.charlson_comorbidity_index,
    CASE WHEN icu.hadm_id IS NOT NULL THEN 'ICU' ELSE 'Non-ICU' END AS icu_status
  FROM
    postop_admissions AS pa
  LEFT JOIN
    `physionet-data.mimiciv_3_1_derived.charlson` AS ch
    ON pa.hadm_id = ch.hadm_id
  LEFT JOIN
    (SELECT DISTINCT hadm_id FROM `physionet-data.mimiciv_3_1_icu.icustays`) AS icu
    ON pa.hadm_id = icu.hadm_id
),
stratified_cohort AS (
  SELECT
    hadm_id,
    hospital_expire_flag,
    length_of_stay,
    icu_status,
    CASE
      WHEN length_of_stay BETWEEN 1 AND 3 THEN '1-3 days'
      WHEN length_of_stay BETWEEN 4 AND 7 THEN '4-7 days'
      WHEN length_of_stay >= 8 THEN '>=8 days'
      ELSE 'Other'
    END AS los_group,
    CASE
      WHEN charlson_comorbidity_index <= 3 THEN '<=3'
      WHEN charlson_comorbidity_index BETWEEN 4 AND 5 THEN '4-5'
      WHEN charlson_comorbidity_index > 5 THEN '>5'
      ELSE 'Unknown'
    END AS charlson_group
  FROM
    cohort_with_scores
)
SELECT
  icu_status,
  los_group,
  charlson_group,
  COUNT(hadm_id) AS admission_count,
  SUM(hospital_expire_flag) AS death_count,
  ROUND(
    SAFE_DIVIDE(SUM(hospital_expire_flag) * 100.0, COUNT(hadm_id)),
    2
  ) AS mortality_rate_pct,
  APPROX_QUANTILES(
    CASE WHEN hospital_expire_flag = 1 THEN length_of_stay END, 2
  )[OFFSET(1)] AS median_time_to_death_days
FROM
  stratified_cohort
WHERE los_group != 'Other'
GROUP BY
  icu_status,
  los_group,
  charlson_group
ORDER BY
  icu_status DESC,
  CASE
    WHEN los_group = '1-3 days' THEN 1
    WHEN los_group = '4-7 days' THEN 2
    WHEN los_group = '>=8 days' THEN 3
  END,
  CASE
    WHEN charlson_group = '<=3' THEN 1
    WHEN charlson_group = '4-5' THEN 2
    WHEN charlson_group = '>5' THEN 3
    ELSE 4
  END;
