WITH trauma_counts AS (
    SELECT
        hadm_id
    FROM
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
        (icd_version = 9 AND icd_code BETWEEN '800' AND '999')
        OR
        (icd_version = 10 AND SUBSTR(icd_code, 1, 1) IN ('S', 'T'))
    GROUP BY
        hadm_id
    HAVING
        COUNT(DISTINCT icd_code) >= 2
),
trauma_admissions AS (
    SELECT
        a.hadm_id,
        a.subject_id,
        CASE
            WHEN a.admission_type LIKE '%EMER%' THEN 'ED Admission'
            WHEN a.admission_type = 'ELECTIVE' THEN 'Elective Admission'
        END AS admission_category,
        CASE
            WHEN DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 1 AND 3 THEN '1-3 days'
            WHEN DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 4 AND 7 THEN '4-7 days'
        END AS stay_category
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    INNER JOIN
        trauma_counts AS tc ON a.hadm_id = tc.hadm_id
    WHERE
        p.gender = 'F'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 73 AND 83
        AND a.dischtime IS NOT NULL AND a.admittime IS NOT NULL
        AND (a.admission_type LIKE '%EMER%' OR a.admission_type = 'ELECTIVE')
        AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 1 AND 7
),
ultrasound_counts AS (
    SELECT
        ta.hadm_id,
        ta.admission_category,
        ta.stay_category,
        COUNT(pr.icd_code) AS num_ultrasounds
    FROM
        trauma_admissions AS ta
    LEFT JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS pr
        ON ta.hadm_id = pr.hadm_id
        AND (
            (pr.icd_version = 9 AND pr.icd_code LIKE '88.7%')
            OR
            (pr.icd_version = 10 AND SUBSTR(pr.icd_code, 1, 1) = 'B' AND SUBSTR(pr.icd_code, 3, 1) = '4')
        )
    GROUP BY
        ta.hadm_id,
        ta.admission_category,
        ta.stay_category
)
SELECT
    admission_category,
    stay_category,
    COUNT(hadm_id) AS num_admissions,
    ROUND(AVG(num_ultrasounds), 2) AS mean_ultrasounds,
    MIN(num_ultrasounds) AS min_ultrasounds,
    MAX(num_ultrasounds) AS max_ultrasounds
FROM
    ultrasound_counts
GROUP BY
    admission_category,
    stay_category
ORDER BY
    admission_category,
    stay_category;
