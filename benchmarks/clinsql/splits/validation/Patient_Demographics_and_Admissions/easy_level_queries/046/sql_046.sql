WITH dapt_admissions AS (
  SELECT
    hadm_id
  FROM
    `physionet-data.mimiciv_3_1_hosp.prescriptions`
  GROUP BY
    hadm_id
  HAVING
    (
      COUNT(CASE WHEN LOWER(drug) LIKE '%clopidogrel%' THEN 1 END) > 0 OR
      COUNT(CASE WHEN LOWER(drug) LIKE '%ticagrelor%' THEN 1 END) > 0 OR
      COUNT(CASE WHEN LOWER(drug) LIKE '%prasugrel%' THEN 1 END) > 0
    )
    AND
    (
      COUNT(CASE WHEN LOWER(drug) LIKE '%aspirin%' THEN 1 END) > 0
    )
),
patient_first_dapt_admission AS (
  SELECT
    a.hospital_expire_flag,
    ROW_NUMBER() OVER(PARTITION BY p.subject_id ORDER BY a.admittime ASC) as admission_rank
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` p
  JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` a
    ON p.subject_id = a.subject_id
  JOIN
    dapt_admissions da
    ON a.hadm_id = da.hadm_id
  WHERE
    p.gender = 'M'
    AND p.anchor_age BETWEEN 37 AND 47
)
SELECT
  STDDEV_SAMP(hospital_expire_flag) AS stddev_in_hospital_mortality
FROM
  patient_first_dapt_admission
WHERE
  admission_rank = 1;
