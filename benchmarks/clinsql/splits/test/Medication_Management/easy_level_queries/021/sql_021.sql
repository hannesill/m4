WITH HighIntensityStatinDurations AS (
  SELECT
    DATE_DIFF(DATE(pr.stoptime), DATE(pr.starttime), DAY) AS duration_days
  FROM `physionet-data.mimiciv_3_1_hosp.patients` p
  JOIN `physionet-data.mimiciv_3_1_hosp.prescriptions` pr
    ON p.subject_id = pr.subject_id
  WHERE
    p.gender = 'F'
    AND p.anchor_age BETWEEN 75 AND 85
    AND LOWER(pr.drug) LIKE '%atorvastatin%'
    AND pr.dose_val_rx IN ('40', '80')
    AND LOWER(pr.dose_unit_rx) = 'mg'
    AND pr.starttime IS NOT NULL
    AND pr.stoptime IS NOT NULL
    AND DATE(pr.starttime) <= DATE(pr.stoptime)
)
SELECT
  ROUND(
    (APPROX_QUANTILES(d.duration_days, 4)[OFFSET(3)]) - (APPROX_QUANTILES(d.duration_days, 4)[OFFSET(1)]),
    2
  ) AS iqr_duration_days
FROM HighIntensityStatinDurations d
WHERE d.duration_days >= 0;
