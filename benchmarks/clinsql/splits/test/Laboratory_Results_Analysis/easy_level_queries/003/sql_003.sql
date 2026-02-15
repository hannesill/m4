WITH acs_admissions AS (
    SELECT DISTINCT adm.hadm_id
    FROM `physionet-data.mimiciv_3_1_hosp.admissions` adm
    JOIN `physionet-data.mimiciv_3_1_hosp.patients` pat
        ON adm.subject_id = pat.subject_id
    JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` dx
        ON adm.hadm_id = dx.hadm_id
    WHERE
        pat.gender = 'M'
        AND
        (
            (dx.icd_version = 9 AND (dx.icd_code LIKE '410%' OR dx.icd_code LIKE '411.1%'))
            OR
            (dx.icd_version = 10 AND (dx.icd_code LIKE 'I20.0%' OR dx.icd_code LIKE 'I21%' OR dx.icd_code LIKE 'I22%'))
        )
),
peak_troponins AS (
    SELECT
        le.hadm_id,
        MAX(le.valuenum) AS peak_troponin_value
    FROM `physionet-data.mimiciv_3_1_hosp.labevents` le
    INNER JOIN acs_admissions acs
        ON le.hadm_id = acs.hadm_id
    WHERE
        le.itemid IN (51003, 51002, 52598)
        AND le.valuenum IS NOT NULL
        AND le.valuenum BETWEEN 0.01 AND 100
    GROUP BY le.hadm_id
)
SELECT
    ROUND(APPROX_QUANTILES(peak_troponin_value, 100)[OFFSET(75)], 2) AS p75_peak_troponin
FROM peak_troponins;
