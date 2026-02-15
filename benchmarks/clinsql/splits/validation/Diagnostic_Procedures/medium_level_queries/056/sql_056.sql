WITH pancreatitis_admissions AS (
    SELECT DISTINCT
        p.subject_id,
        a.hadm_id,
        DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
            ON p.subject_id = a.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
            ON a.hadm_id = d.hadm_id
    WHERE
        p.gender = 'F'
        AND p.anchor_age BETWEEN 47 AND 57
        AND a.dischtime IS NOT NULL AND a.admittime IS NOT NULL
        AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 1 AND 8
        AND (
            (d.icd_version = 9 AND d.icd_code = '5770')
            OR (d.icd_version = 10 AND d.icd_code LIKE 'K85%')
        )
),
imaging_counts AS (
    SELECT
        pa.subject_id,
        pa.hadm_id,
        pa.length_of_stay,
        COUNT(pr.icd_code) AS advanced_imaging_count
    FROM
        pancreatitis_admissions AS pa
    LEFT JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS pr
        ON pa.hadm_id = pr.hadm_id
        AND (
            (pr.icd_version = 9 AND (
                pr.icd_code IN ('8801', '8703', '8741', '8838')
                OR pr.icd_code LIKE '889%'
            ))
            OR (pr.icd_version = 10 AND pr.icd_code LIKE 'B%' AND SUBSTR(pr.icd_code, 3, 1) IN ('0', '1', '2', '3'))
        )
    GROUP BY
        pa.subject_id, pa.hadm_id, pa.length_of_stay
)
SELECT
    CASE
        WHEN ic.length_of_stay BETWEEN 1 AND 4 THEN '1-4 Day Stay'
        WHEN ic.length_of_stay BETWEEN 5 AND 8 THEN '5-8 Day Stay'
    END AS los_group,
    COUNT(DISTINCT ic.subject_id) AS patient_count,
    ROUND(AVG(ic.advanced_imaging_count), 2) AS avg_imaging_procedures_per_admission
FROM
    imaging_counts AS ic
GROUP BY
    los_group
ORDER BY
    los_group;
