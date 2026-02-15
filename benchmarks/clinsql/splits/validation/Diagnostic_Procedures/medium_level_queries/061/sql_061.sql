WITH aki_admissions AS (
    SELECT
        a.hadm_id,
        a.subject_id,
        DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay,
        MAX(CASE WHEN d.seq_num = 1 THEN 1 ELSE 0 END) AS is_primary_aki
    FROM
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.patients` AS p ON a.subject_id = p.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON a.hadm_id = d.hadm_id
    WHERE
        p.gender = 'F'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 64 AND 74
        AND a.dischtime IS NOT NULL AND a.admittime IS NOT NULL AND a.dischtime > a.admittime
        AND (
            (d.icd_version = 9 AND d.icd_code LIKE '584%')
            OR (d.icd_version = 10 AND d.icd_code LIKE 'N17%')
        )
    GROUP BY
        a.hadm_id, a.subject_id, length_of_stay
),
procedure_counts AS (
    SELECT
        aki.hadm_id,
        aki.length_of_stay,
        CASE WHEN aki.is_primary_aki = 1 THEN 'Primary Diagnosis' ELSE 'Secondary Diagnosis' END AS diagnosis_type,
        COUNT(pr.icd_code) AS num_imaging_procedures
    FROM
        aki_admissions AS aki
    LEFT JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS pr ON aki.hadm_id = pr.hadm_id
        AND (
            (pr.icd_version = 9 AND (pr.icd_code LIKE '87%' OR pr.icd_code LIKE '88%'))
            OR (pr.icd_version = 10 AND pr.icd_code LIKE 'B%')
        )
    GROUP BY
        aki.hadm_id, aki.length_of_stay, aki.is_primary_aki
)
SELECT
    CASE
        WHEN pc.length_of_stay BETWEEN 1 AND 3 THEN '1-3 Days'
        WHEN pc.length_of_stay BETWEEN 4 AND 7 THEN '4-7 Days'
    END AS stay_category,
    pc.diagnosis_type,
    COUNT(pc.hadm_id) AS num_admissions,
    APPROX_QUANTILES(pc.num_imaging_procedures, 4)[OFFSET(2)] AS median_imaging_procedures,
    (APPROX_QUANTILES(pc.num_imaging_procedures, 4)[OFFSET(3)] - APPROX_QUANTILES(pc.num_imaging_procedures, 4)[OFFSET(1)]) AS iqr_imaging_procedures
FROM
    procedure_counts AS pc
WHERE
    pc.length_of_stay BETWEEN 1 AND 7
GROUP BY
    stay_category,
    pc.diagnosis_type
ORDER BY
    stay_category,
    pc.diagnosis_type;
