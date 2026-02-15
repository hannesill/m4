WITH asthma_admissions AS (
    SELECT DISTINCT
        adm.hadm_id,
        CASE
            WHEN DATETIME_DIFF(adm.dischtime, adm.admittime, DAY) BETWEEN 1 AND 3 THEN '1-3 Day Stay'
            WHEN DATETIME_DIFF(adm.dischtime, adm.admittime, DAY) BETWEEN 4 AND 7 THEN '4-7 Day Stay'
        END AS stay_category
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS pat
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS adm ON pat.subject_id = adm.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx ON adm.hadm_id = dx.hadm_id
    WHERE
        pat.gender = 'F'
        AND (pat.anchor_age + EXTRACT(YEAR FROM adm.admittime) - pat.anchor_year) BETWEEN 88 AND 98
        AND adm.dischtime IS NOT NULL AND adm.admittime IS NOT NULL
        AND (
            (dx.icd_version = 9 AND dx.icd_code LIKE '493%')
            OR
            (dx.icd_version = 10 AND dx.icd_code LIKE 'J45%')
        )
),
procedure_counts AS (
    SELECT
        aa.hadm_id,
        aa.stay_category,
        COUNT(proc.icd_code) AS num_diagnostic_procedures
    FROM
        asthma_admissions AS aa
    LEFT JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS proc ON aa.hadm_id = proc.hadm_id
        AND (
            (proc.icd_version = 9 AND (proc.icd_code LIKE '87%' OR proc.icd_code LIKE '88%'))
            OR
            (proc.icd_version = 10 AND proc.icd_code LIKE 'B%')
        )
    WHERE
        aa.stay_category IS NOT NULL
    GROUP BY
        aa.hadm_id,
        aa.stay_category
)
SELECT
    pc.stay_category,
    COUNT(pc.hadm_id) AS total_admissions,
    APPROX_QUANTILES(pc.num_diagnostic_procedures, 4)[OFFSET(1)] AS p25_procedures,
    APPROX_QUANTILES(pc.num_diagnostic_procedures, 4)[OFFSET(2)] AS p50_median_procedures,
    APPROX_QUANTILES(pc.num_diagnostic_procedures, 4)[OFFSET(3)] AS p75_procedures
FROM
    procedure_counts AS pc
GROUP BY
    pc.stay_category
ORDER BY
    pc.stay_category;
