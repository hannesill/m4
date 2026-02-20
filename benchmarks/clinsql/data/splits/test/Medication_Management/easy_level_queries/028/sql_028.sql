WITH DAPT_Admissions AS (
  SELECT
    pr.hadm_id
  FROM `physionet-data.mimiciv_3_1_hosp.patients` p
  JOIN `physionet-data.mimiciv_3_1_hosp.prescriptions` pr
    ON p.subject_id = pr.subject_id
  WHERE
    p.gender = 'F'
    AND p.anchor_age BETWEEN 44 AND 54
    AND (
      LOWER(pr.drug) LIKE '%aspirin%' OR
      LOWER(pr.drug) LIKE '%clopidogrel%' OR
      LOWER(pr.drug) LIKE '%ticagrelor%' OR
      LOWER(pr.drug) LIKE '%prasugrel%'
    )
  GROUP BY
    pr.hadm_id
  HAVING
    COUNT(DISTINCT
      CASE
        WHEN LOWER(pr.drug) LIKE '%aspirin%' THEN 'aspirin'
        WHEN LOWER(pr.drug) LIKE '%clopidogrel%' THEN 'clopidogrel'
        WHEN LOWER(pr.drug) LIKE '%ticagrelor%' THEN 'ticagrelor'
        WHEN LOWER(pr.drug) LIKE '%prasugrel%' THEN 'prasugrel'
      END
    ) >= 2
)
SELECT
  ROUND(STDDEV(DATE_DIFF(DATE(pr.stoptime), DATE(pr.starttime), DAY)), 2) AS stddev_dapt_prescription_duration_days
FROM `physionet-data.mimiciv_3_1_hosp.prescriptions` pr
JOIN DAPT_Admissions da ON pr.hadm_id = da.hadm_id
WHERE
  (
    LOWER(pr.drug) LIKE '%aspirin%' OR
    LOWER(pr.drug) LIKE '%clopidogrel%' OR
    LOWER(pr.drug) LIKE '%ticagrelor%' OR
    LOWER(pr.drug) LIKE '%prasugrel%'
  )
  AND pr.starttime IS NOT NULL
  AND pr.stoptime IS NOT NULL
  AND DATE_DIFF(DATE(pr.stoptime), DATE(pr.starttime), DAY) >= 0;
