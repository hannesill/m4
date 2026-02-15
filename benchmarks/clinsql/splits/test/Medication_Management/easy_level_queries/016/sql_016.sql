SELECT
    APPROX_QUANTILES(DATE_DIFF(DATE(pr.stoptime), DATE(pr.starttime), DAY), 100)[OFFSET(25)] as p25_duration_days
FROM
    `physionet-data.mimiciv_3_1_hosp.patients` p
JOIN
    `physionet-data.mimiciv_3_1_hosp.prescriptions` pr ON p.subject_id = pr.subject_id
WHERE
    p.gender = 'M'
    AND p.anchor_age BETWEEN 76 AND 86
    AND pr.starttime IS NOT NULL
    AND pr.stoptime IS NOT NULL
    AND DATE_DIFF(DATE(pr.stoptime), DATE(pr.starttime), DAY) >= 0
    AND (
        LOWER(pr.drug) LIKE '%nitroglycerin%'
        OR LOWER(pr.drug) LIKE '%isosorbide%'
    )
    AND pr.route IN ('IV', 'PO');
