WITH gi_bleed_admissions AS (
    SELECT DISTINCT
        a.hadm_id,
        a.subject_id,
        DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay,
        CASE WHEN icu.stay_id IS NOT NULL THEN 'ICU Stay' ELSE 'No ICU Stay' END AS icu_status
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON a.hadm_id = d.hadm_id
    LEFT JOIN
        (SELECT DISTINCT hadm_id, stay_id FROM `physionet-data.mimiciv_3_1_icu.icustays`) AS icu
        ON a.hadm_id = icu.hadm_id
    WHERE
        p.gender = 'F'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 62 AND 72
        AND a.dischtime IS NOT NULL AND a.admittime IS NOT NULL
        AND (
            (d.icd_version = 9 AND (d.icd_code LIKE '578%' OR d.icd_code = '5693'))
            OR
            (d.icd_version = 10 AND (d.icd_code IN ('K921', 'K922', 'K625')))
        )
),

procedure_counts AS (
    SELECT
        ga.hadm_id,
        ga.icu_status,
        CASE
            WHEN ga.length_of_stay BETWEEN 1 AND 3 THEN '1-3 Day Stay'
            WHEN ga.length_of_stay BETWEEN 4 AND 7 THEN '4-7 Day Stay'
        END AS stay_category,
        COUNT(pr.icd_code) AS diagnostic_procedure_count
    FROM
        gi_bleed_admissions AS ga
    LEFT JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS pr
        ON ga.hadm_id = pr.hadm_id
        AND (
            (pr.icd_version = 9 AND (pr.icd_code LIKE '87%' OR pr.icd_code LIKE '88%' OR pr.icd_code = '8952' OR pr.icd_code LIKE '891%' OR pr.icd_code LIKE '893%'))
            OR
            (pr.icd_version = 10 AND (pr.icd_code LIKE 'B%' OR pr.icd_code LIKE '4A02%' OR pr.icd_code LIKE '4A00%' OR pr.icd_code LIKE '4A06%'))
        )
    WHERE
        ga.length_of_stay BETWEEN 1 AND 7
    GROUP BY
        ga.hadm_id, ga.length_of_stay, ga.icu_status
)

SELECT
    pc.stay_category,
    pc.icu_status,
    COUNT(pc.hadm_id) AS total_admissions,
    ROUND(AVG(pc.diagnostic_procedure_count), 2) AS avg_diagnostics_per_admission,
    MIN(pc.diagnostic_procedure_count) AS min_diagnostics,
    MAX(pc.diagnostic_procedure_count) AS max_diagnostics
FROM
    procedure_counts AS pc
GROUP BY
    pc.stay_category, pc.icu_status
ORDER BY
    pc.stay_category, pc.icu_status;
