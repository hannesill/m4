SELECT
    MIN(DATE_DIFF(DATE(pr.stoptime), DATE(pr.starttime), DAY)) as min_high_intensity_statin_duration_days
FROM
    `physionet-data.mimiciv_3_1_hosp.patients` p
JOIN
    `physionet-data.mimiciv_3_1_hosp.prescriptions` pr ON p.subject_id = pr.subject_id
WHERE
    p.gender = 'F'
    AND p.anchor_age BETWEEN 86 AND 96
    AND LOWER(pr.drug) LIKE '%atorvastatin%'
    AND SAFE_CAST(SPLIT(pr.dose_val_rx, '-')[OFFSET(0)] AS NUMERIC) BETWEEN 40 AND 80
    AND LOWER(pr.dose_unit_rx) = 'mg'
    AND pr.starttime IS NOT NULL
    AND pr.stoptime IS NOT NULL
    AND DATE_DIFF(DATE(pr.stoptime), DATE(pr.starttime), DAY) > 0;
