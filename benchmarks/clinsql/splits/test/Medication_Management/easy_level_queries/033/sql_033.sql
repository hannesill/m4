SELECT
    ROUND(AVG(DATE_DIFF(DATE(pr.stoptime), DATE(pr.starttime), DAY)), 2) as avg_arb_duration_days
FROM `physionet-data.mimiciv_3_1_hosp.patients` p
JOIN `physionet-data.mimiciv_3_1_hosp.prescriptions` pr ON p.subject_id = pr.subject_id
WHERE p.gender = 'F'
  AND p.anchor_age BETWEEN 77 AND 87
  AND pr.starttime IS NOT NULL
  AND pr.stoptime IS NOT NULL
  AND DATE_DIFF(DATE(pr.stoptime), DATE(pr.starttime), DAY) > 0
  AND (
    LOWER(pr.drug) LIKE '%losartan%' OR
    LOWER(pr.drug) LIKE '%valsartan%' OR
    LOWER(pr.drug) LIKE '%irbesartan%' OR
    LOWER(pr.drug) LIKE '%candesartan%' OR
    LOWER(pr.drug) LIKE '%olmesartan%' OR
    LOWER(pr.drug) LIKE '%telmisartan%' OR
    LOWER(pr.drug) LIKE '%azilsartan%'
  );
