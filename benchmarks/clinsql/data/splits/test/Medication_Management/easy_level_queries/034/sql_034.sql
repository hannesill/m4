SELECT
    MAX(DATE_DIFF(DATE(pr.stoptime), DATE(pr.starttime), DAY)) as max_treatment_duration_days
FROM `physionet-data.mimiciv_3_1_hosp.patients` p
JOIN `physionet-data.mimiciv_3_1_hosp.prescriptions` pr ON p.subject_id = pr.subject_id
WHERE p.gender = 'F'
  AND p.anchor_age BETWEEN 51 AND 61
  AND pr.starttime IS NOT NULL
  AND pr.stoptime IS NOT NULL
  AND DATE_DIFF(DATE(pr.stoptime), DATE(pr.starttime), DAY) >= 0
  AND (
    LOWER(pr.drug) LIKE '%hydralazine%' OR
    LOWER(pr.drug) LIKE '%isosorbide dinitrate%'
  );
