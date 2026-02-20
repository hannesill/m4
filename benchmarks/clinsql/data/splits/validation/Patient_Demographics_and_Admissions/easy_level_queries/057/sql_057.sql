WITH
  stroke_admissions AS (
    SELECT DISTINCT hadm_id
    FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      (icd_version = 9 AND SUBSTR(icd_code, 1, 3) BETWEEN '430' AND '437')
      OR
      (icd_version = 10 AND SUBSTR(icd_code, 1, 3) BETWEEN 'I60' AND 'I69')
  ),
  first_stroke_admission_los AS (
    SELECT
      total_icu_los
    FROM (
      SELECT
        p.subject_id,
        a.admittime,
        SUM(icu.los) AS total_icu_los,
        ROW_NUMBER() OVER(PARTITION BY p.subject_id ORDER BY a.admittime ASC) AS admission_rank
      FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
      INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
      INNER JOIN
        stroke_admissions AS sa ON a.hadm_id = sa.hadm_id
      INNER JOIN
        `physionet-data.mimiciv_3_1_icu.icustays` AS icu ON a.hadm_id = icu.hadm_id
      WHERE
        p.gender = 'M'
        AND p.anchor_age BETWEEN 46 AND 56
        AND icu.los IS NOT NULL AND icu.los > 0
      GROUP BY
        p.subject_id, a.hadm_id, a.admittime
    )
    WHERE admission_rank = 1
  )
SELECT
  (APPROX_QUANTILES(total_icu_los, 4))[OFFSET(3)] - (APPROX_QUANTILES(total_icu_los, 4))[OFFSET(1)] AS iqr_icu_los_days
FROM
  first_stroke_admission_los;
