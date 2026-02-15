WITH acs_admissions AS (
    SELECT
        a.hadm_id,
        a.subject_id,
        DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay,
        CASE WHEN MIN(d.seq_num) = 1 THEN 'Primary ACS' ELSE 'Secondary ACS' END AS diagnosis_type
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON a.hadm_id = d.hadm_id
    WHERE
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 39 AND 49
        AND a.dischtime IS NOT NULL AND a.admittime IS NOT NULL
        AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 1 AND 7
        AND (
            (d.icd_version = 9 AND (d.icd_code LIKE '410%' OR d.icd_code = '411.1'))
            OR (d.icd_version = 10 AND (d.icd_code LIKE 'I20.0%' OR d.icd_code LIKE 'I21%' OR d.icd_code LIKE 'I22%' OR d.icd_code LIKE 'I24%'))
        )
    GROUP BY
        a.hadm_id, a.subject_id, a.dischtime, a.admittime
),
ultrasound_counts AS (
    SELECT
        acs.hadm_id,
        acs.diagnosis_type,
        CASE
            WHEN acs.length_of_stay BETWEEN 1 AND 4 THEN '1-4 Day Stay'
            WHEN acs.length_of_stay BETWEEN 5 AND 7 THEN '5-7 Day Stay'
        END AS stay_category,
        COUNT(pr.icd_code) AS num_ultrasounds
    FROM
        acs_admissions AS acs
    LEFT JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS pr ON acs.hadm_id = pr.hadm_id
        AND (
            (pr.icd_version = 9 AND pr.icd_code LIKE '88.7%')
            OR (pr.icd_version = 10 AND SUBSTR(pr.icd_code, 1, 1) = 'B' AND SUBSTR(pr.icd_code, 3, 1) = '1')
        )
    GROUP BY
        acs.hadm_id, acs.diagnosis_type, stay_category
)
SELECT
    diagnosis_type,
    stay_category,
    COUNT(hadm_id) AS admission_count,
    APPROX_QUANTILES(num_ultrasounds, 4)[OFFSET(1)] AS p25_ultrasounds,
    APPROX_QUANTILES(num_ultrasounds, 4)[OFFSET(2)] AS p50_median_ultrasounds,
    APPROX_QUANTILES(num_ultrasounds, 4)[OFFSET(3)] AS p75_ultrasounds
FROM
    ultrasound_counts
GROUP BY
    diagnosis_type, stay_category
ORDER BY
    diagnosis_type, stay_category;
