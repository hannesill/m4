WITH tia_admissions AS (
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
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 50 AND 60
        AND a.admittime IS NOT NULL AND a.dischtime IS NOT NULL
        AND (
            (d.icd_version = 9 AND d.icd_code LIKE '435%')
            OR (d.icd_version = 10 AND d.icd_code LIKE 'G45%')
        )
),
imaging_counts_per_admission AS (
    SELECT
        ta.subject_id,
        ta.hadm_id,
        ta.length_of_stay,
        COUNT(pr.icd_code) AS imaging_procedure_count
    FROM
        tia_admissions AS ta
    LEFT JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS pr
        ON ta.hadm_id = pr.hadm_id
        AND (
            (pr.icd_version = 9 AND (pr.icd_code LIKE '87.%' OR pr.icd_code LIKE '88.9%'))
            OR (pr.icd_version = 10 AND (pr.icd_code LIKE 'B_2%' OR pr.icd_code LIKE 'B_3%'))
        )
    GROUP BY
        ta.subject_id, ta.hadm_id, ta.length_of_stay
)
SELECT
    CASE
        WHEN ic.length_of_stay BETWEEN 1 AND 3 THEN '1-3 Day Stay'
        WHEN ic.length_of_stay BETWEEN 4 AND 7 THEN '4-7 Day Stay'
    END AS los_group,
    COUNT(DISTINCT ic.subject_id) AS patient_count,
    ROUND(AVG(ic.imaging_procedure_count), 2) AS avg_imaging_procedures_per_admission
FROM
    imaging_counts_per_admission AS ic
WHERE
    ic.length_of_stay BETWEEN 1 AND 7
GROUP BY
    los_group
ORDER BY
    los_group;
