SELECT
    APPROX_QUANTILES(DATE_DIFF(DATE(pr.stoptime), DATE(pr.starttime), DAY), 100)[OFFSET(75)] AS p75_duration_days
FROM
    `physionet-data.mimiciv_3_1_hosp.patients` p
JOIN
    `physionet-data.mimiciv_3_1_hosp.prescriptions` pr ON p.subject_id = pr.subject_id
WHERE
    p.gender = 'M'
    AND p.anchor_age BETWEEN 38 AND 48
    AND pr.starttime IS NOT NULL
    AND pr.stoptime IS NOT NULL
    AND DATE_DIFF(DATE(pr.stoptime), DATE(pr.starttime), DAY) >= 0
    AND (
        LOWER(pr.drug) LIKE '%losartan%' OR
        LOWER(pr.drug) LIKE '%valsartan%' OR
        LOWER(pr.drug) LIKE '%irbesartan%' OR
        LOWER(pr.drug) LIKE '%candesartan%' OR
        LOWER(pr.drug) LIKE '%olmesartan%' OR
        LOWER(pr.drug) LIKE '%telmisartan%'
    );
