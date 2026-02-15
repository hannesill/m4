WITH AmiodaroneDurations AS (
  SELECT
      DATE_DIFF(DATE(pr.stoptime), DATE(pr.starttime), DAY) AS treatment_duration_days
  FROM `physionet-data.mimiciv_3_1_hosp.patients` p
  JOIN `physionet-data.mimiciv_3_1_hosp.prescriptions` pr ON p.subject_id = pr.subject_id
  WHERE
      p.gender = 'M'
      AND p.anchor_age BETWEEN 62 AND 72
      AND LOWER(pr.drug) LIKE '%amiodarone%'
      AND pr.starttime IS NOT NULL
      AND pr.stoptime IS NOT NULL
      AND DATE_DIFF(DATE(pr.stoptime), DATE(pr.starttime), DAY) > 0
)
SELECT
    (APPROX_QUANTILES(treatment_duration_days, 100)[OFFSET(75)] - APPROX_QUANTILES(treatment_duration_days, 100)[OFFSET(25)]) AS iqr_amiodarone_duration_days
FROM AmiodaroneDurations;
