SELECT APPROX_QUANTILES(DATE_DIFF(DATE(pr.stoptime), DATE(pr.starttime), DAY), 4)[OFFSET(1)] AS p25_duration_days
FROM `physionet-data.mimiciv_3_1_hosp.patients` p
JOIN `physionet-data.mimiciv_3_1_hosp.prescriptions` pr ON p.subject_id = pr.subject_id
WHERE p.gender = 'F'
  AND p.anchor_age BETWEEN 50 AND 60
  AND pr.starttime IS NOT NULL
  AND pr.stoptime IS NOT NULL
  AND DATE_DIFF(DATE(pr.stoptime), DATE(pr.starttime), DAY) >= 0
  AND (
    LOWER(pr.drug) LIKE '%lisinopril%' OR
    LOWER(pr.drug) LIKE '%enalapril%' OR
    LOWER(pr.drug) LIKE '%ramipril%' OR
    LOWER(pr.drug) LIKE '%captopril%' OR
    LOWER(pr.drug) LIKE '%benazepril%' OR
    LOWER(pr.drug) LIKE '%quinapril%'
  );
