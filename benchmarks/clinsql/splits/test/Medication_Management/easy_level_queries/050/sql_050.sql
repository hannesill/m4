SELECT
    ROUND(AVG(DATE_DIFF(DATE(pr.stoptime), DATE(pr.starttime), DAY)), 2) as avg_prescription_duration_days
FROM `physionet-data.mimiciv_3_1_hosp.patients` p
JOIN `physionet-data.mimiciv_3_1_hosp.prescriptions` pr ON p.subject_id = pr.subject_id
WHERE
    p.gender = 'M'
    AND p.anchor_age BETWEEN 64 AND 74
    AND (
        LOWER(pr.drug) LIKE '%spironolactone%'
        OR LOWER(pr.drug) LIKE '%eplerenone%'
    )
    AND pr.starttime IS NOT NULL
    AND pr.stoptime IS NOT NULL
    AND DATE_DIFF(DATE(pr.stoptime), DATE(pr.starttime), DAY) > 0;
