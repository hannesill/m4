WITH prescription_durations AS (
  SELECT
    DATE_DIFF(DATE(pr.stoptime), DATE(pr.starttime), DAY) as duration_days
  FROM `physionet-data.mimiciv_3_1_hosp.patients` p
  JOIN `physionet-data.mimiciv_3_1_hosp.prescriptions` pr ON p.subject_id = pr.subject_id
  WHERE
    p.gender = 'F'
    AND p.anchor_age BETWEEN 90 AND 100
    AND pr.starttime IS NOT NULL
    AND pr.stoptime IS NOT NULL
    AND DATE_DIFF(DATE(pr.stoptime), DATE(pr.starttime), DAY) >= 0
    AND (
      LOWER(pr.drug) LIKE '%hydrochlorothiazide%' OR
      LOWER(pr.drug) LIKE '%hctz%' OR
      LOWER(pr.drug) LIKE '%chlorthalidone%' OR
      LOWER(pr.drug) LIKE '%metolazone%' OR
      LOWER(pr.drug) LIKE '%indapamide%'
    )
)
SELECT
  ROUND(
    (APPROX_QUANTILES(duration_days, 4)[OFFSET(3)]) - (APPROX_QUANTILES(duration_days, 4)[OFFSET(1)]),
    2
  ) AS iqr_duration_days
FROM prescription_durations;
