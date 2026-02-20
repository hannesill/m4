WITH FirstAKIAmission AS (
  SELECT
    p.subject_id,
    a.admittime,
    a.dischtime,
    ROW_NUMBER() OVER(PARTITION BY p.subject_id ORDER BY a.admittime ASC) as admission_rank
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` p
  JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` a
    ON p.subject_id = a.subject_id
  WHERE
    p.gender = 'F'
    AND p.anchor_age BETWEEN 70 AND 80
    AND a.dischtime IS NOT NULL
    AND EXISTS (
      SELECT 1
      FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` d
      WHERE a.hadm_id = d.hadm_id
        AND (d.icd_code LIKE 'N17%' OR d.icd_code LIKE '584%')
    )
)
SELECT
  STDDEV_SAMP(DATE_DIFF(DATE(dischtime), DATE(admittime), DAY)) AS stddev_length_of_stay
FROM
  FirstAKIAmission
WHERE
  admission_rank = 1;
