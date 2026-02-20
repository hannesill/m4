SELECT
    APPROX_QUANTILES(DATE_DIFF(DATE(pr.stoptime), DATE(pr.starttime), DAY), 100)[OFFSET(25)] AS p25_duration_days
FROM
    `physionet-data.mimiciv_3_1_hosp.patients` p
JOIN
    `physionet-data.mimiciv_3_1_hosp.prescriptions` pr ON p.subject_id = pr.subject_id
WHERE
    p.gender = 'F'
    AND p.anchor_age BETWEEN 81 AND 91
    AND pr.starttime IS NOT NULL
    AND pr.stoptime IS NOT NULL
    AND DATE_DIFF(DATE(pr.stoptime), DATE(pr.starttime), DAY) >= 0
    AND (
        LOWER(pr.drug) LIKE '%amlodipine%' OR
        LOWER(pr.drug) LIKE '%nifedipine%' OR
        LOWER(pr.drug) LIKE '%felodipine%' OR
        LOWER(pr.drug) LIKE '%nicardipine%'
    );
