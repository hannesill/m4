SELECT
    APPROX_QUANTILES(a.hospital_expire_flag, 4)[OFFSET(3)] - APPROX_QUANTILES(a.hospital_expire_flag, 4)[OFFSET(1)] AS iqr_in_hospital_mortality
FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    ON p.subject_id = a.subject_id
WHERE
    p.gender = 'F'
    AND p.anchor_age BETWEEN 51 AND 61
    AND a.dischtime IS NOT NULL;
