WITH PrescriptionDurations AS (
  SELECT
    DATE_DIFF(DATE(pr.stoptime), DATE(pr.starttime), DAY) AS duration_days
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` p
  JOIN
    `physionet-data.mimiciv_3_1_hosp.prescriptions` pr
    ON p.subject_id = pr.subject_id
  WHERE
    p.gender = 'F'
    AND p.anchor_age BETWEEN 59 AND 69
    AND LOWER(pr.drug) LIKE '%amiodarone%'
    AND pr.starttime IS NOT NULL
    AND pr.stoptime IS NOT NULL
    AND DATE_DIFF(DATE(pr.stoptime), DATE(pr.starttime), DAY) >= 0
)
SELECT
  (APPROX_QUANTILES(duration_days, 4)[OFFSET(3)]) - (APPROX_QUANTILES(duration_days, 4)[OFFSET(1)]) AS iqr_duration_days
FROM
  PrescriptionDurations;
