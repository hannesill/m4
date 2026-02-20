WITH acs_admissions AS (
    SELECT DISTINCT
        adm.hadm_id
    FROM `physionet-data.mimiciv_3_1_hosp.patients` p
    JOIN `physionet-data.mimiciv_3_1_hosp.admissions` adm
        ON p.subject_id = adm.subject_id
    JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` dx
        ON adm.hadm_id = dx.hadm_id
    WHERE
        p.gender = 'F'
        AND (
            dx.icd_version = 9 AND (
                   STARTS_WITH(dx.icd_code, '410')
                OR dx.icd_code = '4111'
            )
            OR
            dx.icd_version = 10 AND (
                   STARTS_WITH(dx.icd_code, 'I200')
                OR STARTS_WITH(dx.icd_code, 'I21')
                OR STARTS_WITH(dx.icd_code, 'I22')
            )
        )
),
nadir_troponins AS (
    SELECT
        le.hadm_id,
        MIN(le.valuenum) as nadir_troponin
    FROM `physionet-data.mimiciv_3_1_hosp.labevents` le
    INNER JOIN acs_admissions aa ON le.hadm_id = aa.hadm_id
    WHERE
        le.itemid IN (
            51003,
            51002,
            52598
        )
        AND le.valuenum IS NOT NULL
        AND le.valuenum BETWEEN 0 AND 100
    GROUP BY
        le.hadm_id
)
SELECT
    ROUND(APPROX_QUANTILES(nadir_troponin, 100)[OFFSET(25)], 3) AS p25_nadir_troponin
FROM nadir_troponins;
