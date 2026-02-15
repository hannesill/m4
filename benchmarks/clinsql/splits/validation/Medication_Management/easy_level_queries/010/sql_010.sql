SELECT
    ROUND(STDDEV_SAMP(DATE_DIFF(DATE(pr.stoptime), DATE(pr.starttime), DAY)), 2) as stddev_duration_days
FROM `physionet-data.mimiciv_3_1_hosp.patients` p
JOIN `physionet-data.mimiciv_3_1_hosp.prescriptions` pr ON p.subject_id = pr.subject_id
WHERE
    p.gender = 'F'
    AND p.anchor_age BETWEEN 73 AND 83
    AND pr.starttime IS NOT NULL
    AND pr.stoptime IS NOT NULL
    AND DATE_DIFF(DATE(pr.stoptime), DATE(pr.starttime), DAY) >= 0
    AND (
        LOWER(pr.drug) LIKE '%nitroglycerin%'
        OR LOWER(pr.drug) LIKE '%isosorbide%'
    );
