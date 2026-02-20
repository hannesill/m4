WITH DAPT_Admissions AS (
  SELECT
    hadm_id
  FROM
    `physionet-data.mimiciv_3_1_hosp.prescriptions`
  WHERE
    starttime IS NOT NULL AND stoptime IS NOT NULL
  GROUP BY
    hadm_id
  HAVING
    SUM(CASE WHEN LOWER(drug) LIKE '%aspirin%' THEN 1 ELSE 0 END) > 0
    AND
    SUM(CASE WHEN
      LOWER(drug) LIKE '%clopidogrel%' OR
      LOWER(drug) LIKE '%ticagrelor%' OR
      LOWER(drug) LIKE '%prasugrel%'
    THEN 1 ELSE 0 END) > 0
)
SELECT
  MAX(DATE_DIFF(DATE(pr.stoptime), DATE(pr.starttime), DAY)) as max_dapt_prescription_duration_days
FROM
  `physionet-data.mimiciv_3_1_hosp.patients` p
JOIN
  `physionet-data.mimiciv_3_1_hosp.prescriptions` pr ON p.subject_id = pr.subject_id
JOIN
  DAPT_Admissions da ON pr.hadm_id = da.hadm_id
WHERE
  p.gender = 'M'
  AND p.anchor_age BETWEEN 84 AND 94
  AND pr.starttime IS NOT NULL
  AND pr.stoptime IS NOT NULL
  AND DATE_DIFF(DATE(pr.stoptime), DATE(pr.starttime), DAY) >= 0
  AND (
    LOWER(pr.drug) LIKE '%aspirin%' OR
    LOWER(pr.drug) LIKE '%clopidogrel%' OR
    LOWER(pr.drug) LIKE '%ticagrelor%' OR
    LOWER(pr.drug) LIKE '%prasugrel%'
  );
