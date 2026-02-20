SELECT
    APPROX_QUANTILES(DATE_DIFF(DATE(icu.outtime), DATE(icu.intime), DAY), 100)[OFFSET(50)] AS median_icu_los_days
FROM
    `physionet-data.mimiciv_3_1_icu.icustays` AS icu
INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
    ON icu.subject_id = p.subject_id
WHERE
    p.gender = 'F'
    AND p.anchor_age BETWEEN 35 AND 45
    AND icu.outtime IS NOT NULL
    AND EXISTS (
        SELECT 1
        FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
        WHERE
            dx.hadm_id = icu.hadm_id
            AND (
                (dx.icd_version = 9 AND SUBSTR(dx.icd_code, 1, 3) BETWEEN '430' AND '438')
                OR
                (dx.icd_version = 10 AND SUBSTR(dx.icd_code, 1, 3) BETWEEN 'I60' AND 'I69')
            )
    );
