WITH ugib_admissions AS (
    SELECT DISTINCT
        adm.hadm_id,
        DATETIME_DIFF(adm.dischtime, adm.admittime, DAY) AS length_of_stay
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS pat
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
        ON pat.subject_id = adm.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
        ON adm.hadm_id = dx.hadm_id
    WHERE
        pat.gender = 'F'
        AND pat.anchor_age BETWEEN 53 AND 63
        AND adm.dischtime IS NOT NULL AND adm.admittime IS NOT NULL
        AND DATETIME_DIFF(adm.dischtime, adm.admittime, DAY) BETWEEN 1 AND 8
        AND (
            (dx.icd_version = 9 AND dx.icd_code LIKE '578%')
            OR
            (dx.icd_version = 10 AND dx.icd_code IN ('K920', 'K921', 'K922'))
        )
),
procedure_counts AS (
    SELECT
        ua.hadm_id,
        CASE
            WHEN ua.length_of_stay BETWEEN 1 AND 4 THEN '1-4 Day Stay'
            WHEN ua.length_of_stay BETWEEN 5 AND 8 THEN '5-8 Day Stay'
        END AS stay_category,
        COUNT(proc.icd_code) AS num_diagnostic_procedures
    FROM
        ugib_admissions AS ua
    LEFT JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS proc
        ON ua.hadm_id = proc.hadm_id
        AND (
            (proc.icd_version = 9 AND proc.icd_code LIKE '87%')
            OR (proc.icd_version = 9 AND proc.icd_code LIKE '88%')
            OR (proc.icd_version = 10 AND proc.icd_code LIKE 'B%')
        )
    GROUP BY
        ua.hadm_id, ua.length_of_stay
)
SELECT
    pc.stay_category,
    COUNT(pc.hadm_id) AS num_admissions,
    APPROX_QUANTILES(pc.num_diagnostic_procedures, 4)[OFFSET(1)] AS p25_procedures,
    APPROX_QUANTILES(pc.num_diagnostic_procedures, 4)[OFFSET(2)] AS p50_median_procedures,
    APPROX_QUANTILES(pc.num_diagnostic_procedures, 4)[OFFSET(3)] AS p75_procedures
FROM
    procedure_counts AS pc
GROUP BY
    pc.stay_category
ORDER BY
    pc.stay_category;
