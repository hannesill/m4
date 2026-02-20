SELECT
    APPROX_QUANTILES(DATE_DIFF(DATE(pr.stoptime), DATE(pr.starttime), DAY), 2)[OFFSET(1)] AS median_anticoagulant_duration_days
FROM `physionet-data.mimiciv_3_1_hosp.patients` p
JOIN `physionet-data.mimiciv_3_1_hosp.prescriptions` pr ON p.subject_id = pr.subject_id
WHERE
    p.gender = 'M'
    AND p.anchor_age BETWEEN 58 AND 68
    AND pr.starttime IS NOT NULL
    AND pr.stoptime IS NOT NULL
    AND DATE_DIFF(DATE(pr.stoptime), DATE(pr.starttime), DAY) >= 0
    AND (
        LOWER(pr.drug) LIKE '%heparin%' OR
        LOWER(pr.drug) LIKE '%enoxaparin%'
    );
