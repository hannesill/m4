WITH pneumonia_admissions AS (
  SELECT DISTINCT hadm_id
  FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
  WHERE
    (icd_version = 9 AND SUBSTR(icd_code, 1, 3) BETWEEN '480' AND '486')
    OR
    (icd_version = 10 AND SUBSTR(icd_code, 1, 3) BETWEEN 'J12' AND 'J18')
),
patient_first_admission_los AS (
  SELECT
    p.subject_id,
    SUM(icu.los) AS total_icu_los_days,
    ROW_NUMBER() OVER(PARTITION BY p.subject_id ORDER BY a.admittime ASC) as admission_rank
  FROM `physionet-data.mimiciv_3_1_hosp.patients` AS p
  JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    ON p.subject_id = a.subject_id
  JOIN `physionet-data.mimiciv_3_1_icu.icustays` AS icu
    ON a.hadm_id = icu.hadm_id
  JOIN pneumonia_admissions AS pa
    ON a.hadm_id = pa.hadm_id
  WHERE
    p.gender = 'M'
    AND p.anchor_age BETWEEN 51 AND 61
    AND icu.los IS NOT NULL AND icu.los > 0
  GROUP BY
    p.subject_id, a.hadm_id, a.admittime
)
SELECT
  APPROX_QUANTILES(total_icu_los_days, 100)[OFFSET(25)] AS p25_icu_los_days
FROM patient_first_admission_los
WHERE
  admission_rank = 1;
