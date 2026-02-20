SELECT
    MAX(DATE_DIFF(DATE(pr.stoptime), DATE(pr.starttime), DAY)) as max_nitrate_duration_days
FROM `physionet-data.mimiciv_3_1_hosp.patients` p
JOIN `physionet-data.mimiciv_3_1_hosp.prescriptions` pr ON p.subject_id = pr.subject_id
WHERE
    p.gender = 'F'
    AND p.anchor_age BETWEEN 80 AND 90
    AND (
        LOWER(pr.drug) LIKE '%nitroglycerin%'
        OR LOWER(pr.drug) LIKE '%isosorbide%'
    )
    AND pr.route IN ('IV', 'PO', 'SL')
    AND pr.starttime IS NOT NULL
    AND pr.stoptime IS NOT NULL
    AND DATE_DIFF(DATE(pr.stoptime), DATE(pr.starttime), DAY) >= 0;
